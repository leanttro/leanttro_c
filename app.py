from flask import Flask, render_template, request, jsonify, abort
from models import db, Produto, Pedido, ItemPedido
from emails import email_pedido_confirmado, email_pedido_enviado, email_novo_pedido_admin
from filters import register_filters
from dotenv import load_dotenv
import os, requests, json, hmac, hashlib
from datetime import datetime
from decimal import Decimal

load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')
db.init_app(app)
register_filters(app)

MP_TOKEN = os.getenv('MP_ACCESS_TOKEN')
ME_TOKEN = os.getenv('MELHORENVIO_TOKEN')
ME_URL   = os.getenv('MELHORENVIO_URL', 'https://melhorenvio.com.br/api/v2')
CEP_ORIGEM = os.getenv('CEP_ORIGEM', '01026000')
BASE_URL = os.getenv('BASE_URL', 'https://cestadepresentes.com.br')

def gerar_numero_pedido():
    hoje = datetime.utcnow().strftime('%Y%m%d')
    count = Pedido.query.filter(Pedido.numero.like(f'CP-{hoje}-%')).count()
    return f"CP-{hoje}-{str(count+1).zfill(3)}"

# ─── ROTAS PÚBLICAS ──────────────────────────────────────────────

@app.route('/')
def index():
    produtos = Produto.query.filter_by(ativo=True).order_by(Produto.preco).all()
    return render_template('index.html', produtos=produtos)

@app.route('/produto/<slug>')
def produto(slug):
    p = Produto.query.filter_by(slug=slug, ativo=True).first_or_404()
    outros = Produto.query.filter(Produto.ativo==True, Produto.id!=p.id).limit(2).all()
    return render_template('produto.html', produto=p, outros=outros)

@app.route('/checkout')
def checkout():
    return render_template('checkout.html')

@app.route('/obrigado/<numero>')
def obrigado(numero):
    pedido = Pedido.query.filter_by(numero=numero).first_or_404()
    return render_template('obrigado.html', pedido=pedido)

# ─── API: FRETE ──────────────────────────────────────────────────

@app.route('/api/frete', methods=['POST'])
def calcular_frete():
    data = request.json
    cep = data.get('cep', '').replace('-', '')
    produto_id = data.get('produto_id')
    
    if not cep or len(cep) != 8:
        return jsonify({'erro': 'CEP inválido'}), 400

    produto = Produto.query.get(produto_id)
    if not produto:
        return jsonify({'erro': 'Produto não encontrado'}), 404

    headers = {
        'Authorization': f'Bearer {ME_TOKEN}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'cestadepresentes.com.br (contato@cestadepresentes.com.br)'
    }

    payload = {
        'from': {'postal_code': CEP_ORIGEM},
        'to': {'postal_code': cep},
        'package': {
            'height': produto.altura,
            'width': produto.largura,
            'length': produto.comprimento,
            'weight': produto.peso
        },
        'options': {'insurance_value': float(produto.preco), 'receipt': False, 'own_hand': False},
        'services': '1,2,17'  # PAC, SEDEX, Mini
    }

    try:
        resp = requests.post(f'{ME_URL}/me/shipment/calculate', json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            return jsonify({'erro': 'Erro ao calcular frete'}), 502
        
        opcoes = []
        for s in resp.json():
            if s.get('error') or not s.get('price'):
                continue
            opcoes.append({
                'id': s['id'],
                'nome': s['name'],
                'empresa': s['company']['name'],
                'preco': float(s['price']),
                'prazo': s.get('delivery_time', 7),
                'logo': s['company'].get('picture', '')
            })
        
        opcoes.sort(key=lambda x: x['preco'])
        return jsonify(opcoes)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ─── API: CRIAR PREFERÊNCIA MERCADO PAGO ─────────────────────────

@app.route('/api/criar-preferencia', methods=['POST'])
def criar_preferencia():
    data = request.json
    produto = Produto.query.get(data.get('produto_id'))
    if not produto:
        return jsonify({'erro': 'Produto não encontrado'}), 404

    valor_frete = Decimal(str(data.get('valor_frete', 0)))
    total = produto.preco + valor_frete

    # Salva pedido como pendente
    pedido = Pedido(
        numero=gerar_numero_pedido(),
        nome=data['nome'],
        email=data['email'],
        telefone=data.get('telefone', ''),
        tipo_entrega=data.get('tipo_entrega', 'retirada'),
        cep=data.get('cep', ''),
        endereco=data.get('endereco', ''),
        servico_frete=data.get('servico_frete', ''),
        valor_frete=valor_frete,
        valor_total=total,
        mensagem=data.get('mensagem', ''),
        status='pending'
    )
    db.session.add(pedido)
    db.session.flush()

    item = ItemPedido(
        pedido_id=pedido.id,
        produto_id=produto.id,
        nome_produto=produto.nome,
        preco_unitario=produto.preco,
        quantidade=1
    )
    db.session.add(item)
    db.session.commit()

    # Cria preferência no MP
    preference = {
        'items': [{
            'title': produto.nome,
            'quantity': 1,
            'unit_price': float(total),
            'currency_id': 'BRL'
        }],
        'payer': {'name': data['nome'], 'email': data['email']},
        'back_urls': {
            'success': f'{BASE_URL}/obrigado/{pedido.numero}',
            'failure': f'{BASE_URL}/checkout?erro=pagamento',
            'pending': f'{BASE_URL}/obrigado/{pedido.numero}'
        },
        'auto_return': 'approved',
        'external_reference': pedido.id,
        'notification_url': f'{BASE_URL}/api/webhook/mp',
        'statement_descriptor': 'CESTADEPRESENTES',
        'expires': False
    }

    resp = requests.post(
        'https://api.mercadopago.com/checkout/preferences',
        json=preference,
        headers={'Authorization': f'Bearer {MP_TOKEN}', 'Content-Type': 'application/json'}
    )

    if resp.status_code != 201:
        return jsonify({'erro': 'Erro ao criar preferência MP'}), 502

    pref_data = resp.json()
    pedido.mp_preference_id = pref_data['id']
    db.session.commit()

    return jsonify({
        'preference_id': pref_data['id'],
        'init_point': pref_data['init_point'],
        'numero': pedido.numero
    })

# ─── WEBHOOK MERCADO PAGO ─────────────────────────────────────────

@app.route('/api/webhook/mp', methods=['POST'])
def webhook_mp():
    data = request.json or {}
    topic = data.get('type') or request.args.get('topic')
    resource_id = data.get('data', {}).get('id') or request.args.get('id')

    if topic == 'payment' and resource_id:
        resp = requests.get(
            f'https://api.mercadopago.com/v1/payments/{resource_id}',
            headers={'Authorization': f'Bearer {MP_TOKEN}'}
        )
        if resp.status_code == 200:
            payment = resp.json()
            pedido_id = payment.get('external_reference')
            status_mp = payment.get('status')  # approved, rejected, pending

            if pedido_id:
                pedido = Pedido.query.get(pedido_id)
                if pedido:
                    pedido.mp_payment_id = str(resource_id)
                    if status_mp == 'approved' and pedido.status != 'paid':
                        pedido.status = 'paid'
                        db.session.commit()
                        # Envia e-mails
                        email_pedido_confirmado(pedido, pedido.itens)
                        email_novo_pedido_admin(pedido, pedido.itens)
                    elif status_mp in ('rejected', 'cancelled'):
                        pedido.status = 'cancelled'
                    db.session.commit()

    return jsonify({'status': 'ok'}), 200

# ─── ADMIN ───────────────────────────────────────────────────────

@app.route('/admin')
def admin():
    pedidos = Pedido.query.order_by(Pedido.criado_em.desc()).limit(100).all()
    return render_template('admin.html', pedidos=pedidos)

@app.route('/admin/pedido/<pedido_id>/rastreio', methods=['POST'])
def atualizar_rastreio(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.codigo_rastreio = request.json.get('codigo')
    pedido.status = 'enviado'
    db.session.commit()
    email_pedido_enviado(pedido)
    return jsonify({'ok': True})

@app.route('/admin/pedido/<pedido_id>/status', methods=['POST'])
def atualizar_status(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.status = request.json.get('status')
    db.session.commit()
    return jsonify({'ok': True})

# ─── INICIALIZAÇÃO ────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    # Seed dos 3 produtos se não existirem
    if Produto.query.count() == 0:
        produtos_seed = [
            Produto(
                nome='Café com Carinho',
                slug='cafe-com-carinho',
                descricao='Uma cestinha especial com os melhores produtos para um café da manhã inesquecível. Perfeita para surpreender quem você ama com um presente cheio de carinho.',
                itens=json.dumps(['Cestinha de palha', 'Biscoito recheado', 'Torrada', 'Geleia importada', 'Achocolatado', 'Caneca', 'Chocolate', 'Laço e embalagem']),
                preco=Decimal('119.00'),
                imagem='/static/img/cesta1.jpg',
                peso=1.5, altura=20, largura=25, comprimento=25
            ),
            Produto(
                nome='Manhã Especial',
                slug='manha-especial',
                descricao='Nossa cesta mais vendida! Tudo que você precisa para uma manhã perfeita, com itens selecionados e toque personalizado com o nome do presenteado.',
                itens=json.dumps(['Tudo da Cesta Básica', 'Suco natural', 'Mel', 'Cookie artesanal', 'Nutella', 'Tag personalizada com nome', 'Papel de seda premium']),
                preco=Decimal('189.00'),
                imagem='/static/img/cesta2.jpg',
                peso=2.5, altura=25, largura=30, comprimento=30
            ),
            Produto(
                nome='Grande Amor',
                slug='grande-amor',
                descricao='O presente mais completo e luxuoso para momentos verdadeiramente especiais. Caixa premium com espumante, chocolates finos e muito mais.',
                itens=json.dumps(['Tudo da Cesta Intermediária', 'Espumante Chandon Mini', 'Ferrero Rocher (3un)', 'Vela aromática', 'Caixa kraft premium', 'Fita cetim e laço elaborado']),
                preco=Decimal('329.00'),
                imagem='/static/img/cesta3.jpg',
                peso=4.0, altura=30, largura=35, comprimento=35
            ),
        ]
        for p in produtos_seed:
            db.session.add(p)
        db.session.commit()
        print("✅ Produtos criados!")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
