from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for
from models import db, Produto, Pedido, ItemPedido, Sorteio, NumeroSorteio, Agendamento, BloqueioHorario, ConfigAgenda
from emails import email_pedido_confirmado, email_pedido_enviado, email_novo_pedido_admin
from filters import register_filters
from dotenv import load_dotenv
import os, requests, json, bcrypt
from datetime import datetime, date, timedelta
from decimal import Decimal

load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')
db.init_app(app)
register_filters(app)

MP_TOKEN  = os.getenv('MP_ACCESS_TOKEN')
ME_TOKEN  = os.getenv('MELHORENVIO_TOKEN')
ME_URL    = os.getenv('MELHORENVIO_URL', 'https://melhorenvio.com.br/api/v2')
CEP_ORIGEM = os.getenv('CEP_ORIGEM', '01026000')
BASE_URL  = os.getenv('BASE_URL', 'https://cestadepresentes.com.br')

def gerar_numero_pedido():
    hoje = datetime.utcnow().strftime('%Y%m%d')
    count = Pedido.query.filter(Pedido.numero.like(f'CP-{hoje}-%')).count()
    return f"CP-{hoje}-{str(count+1).zfill(3)}"

def admin_logado():
    return session.get('admin_id') is not None

# ─── HELPERS DE AGENDA ────────────────────────────────────────────

def get_config_agenda():
    config = ConfigAgenda.query.first()
    if not config:
        config = ConfigAgenda()
        db.session.add(config)
        db.session.commit()
    return config

def horarios_disponiveis(pedido_pago_em=None):
    """
    Retorna lista de dicts {'data': date, 'hora': int} disponíveis
    a partir de agora + tempo de preparo, respeitando config e bloqueios.
    Retorna os próximos 7 dias úteis com slots livres.
    """
    config = get_config_agenda()
    minutos_preparo = config.minutos_preparo
    hora_abertura = config.hora_abertura
    hora_fechamento = config.hora_fechamento
    max_por_slot = config.max_por_horario
    dias_permitidos = [int(d) for d in config.dias_semana.split(',')]

    agora = datetime.now()
    mais_cedo = agora + timedelta(minutes=minutos_preparo)

    # Coleta bloqueios dos próximos 14 dias
    ate = date.today() + timedelta(days=14)
    bloqueios = BloqueioHorario.query.filter(
        BloqueioHorario.data >= date.today(),
        BloqueioHorario.data <= ate
    ).all()

    def dia_bloqueado(d):
        for b in bloqueios:
            if b.data == d and b.hora_inicio is None:
                return True
        return False

    def hora_bloqueada(d, h):
        for b in bloqueios:
            if b.data == d and b.hora_inicio is not None:
                if b.hora_inicio <= h < b.hora_fim:
                    return True
        return False

    slots_disponiveis = []
    dia_atual = date.today()

    for _ in range(14):  # varre até 14 dias à frente
        if dia_atual.weekday() + 1 in dias_permitidos or (dia_atual.weekday() == 6 and 0 in dias_permitidos):
            # weekday(): 0=seg,...,6=dom — nossa convenção: 0=dom,1=seg,...,6=sab
            dia_semana_conv = (dia_atual.weekday() + 1) % 7  # converte: seg=1,...,dom=0
            if dia_semana_conv in dias_permitidos and not dia_bloqueado(dia_atual):
                for hora in range(hora_abertura, hora_fechamento):
                    dt_slot = datetime.combine(dia_atual, datetime.min.time()).replace(hour=hora)
                    if dt_slot <= mais_cedo:
                        continue
                    if hora_bloqueada(dia_atual, hora):
                        continue
                    # Conta agendamentos já existentes neste slot
                    ocupados = Agendamento.query.filter_by(
                        data_retirada=dia_atual,
                        hora_retirada=hora
                    ).filter(Agendamento.status != 'cancelado').count()
                    if ocupados < max_por_slot:
                        slots_disponiveis.append({
                            'data': dia_atual.isoformat(),
                            'hora': hora,
                            'label': f"{dia_atual.strftime('%d/%m/%Y')} às {hora:02d}:00"
                        })
        dia_atual += timedelta(days=1)

    return slots_disponiveis

# ─── ROTAS PÚBLICAS ──────────────────────────────────────────────

@app.route('/')
def index():
    produtos = Produto.query.filter_by(ativo=True).order_by(Produto.preco).all()
    sorteio = Sorteio.query.filter_by(ativo=True).first()
    return render_template('index.html', produtos=produtos, sorteio=sorteio)

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

# ─── AGENDAMENTO PÚBLICO ─────────────────────────────────────────

@app.route('/agendar/<numero>')
def agendar(numero):
    """Página pós-pagamento onde o cliente escolhe o horário de retirada."""
    pedido = Pedido.query.filter_by(numero=numero).first_or_404()
    if pedido.status != 'paid':
        return render_template('agendar.html', pedido=pedido, slots=[], erro='Pagamento ainda não confirmado.')
    slots = horarios_disponiveis(pedido_pago_em=pedido.criado_em)
    return render_template('agendar.html', pedido=pedido, slots=slots, erro=None)

@app.route('/api/agendar', methods=['POST'])
def api_agendar():
    """Cliente confirma ou remarca o horário de retirada."""
    data = request.json
    numero = data.get('numero')
    data_retirada = data.get('data')  # 'YYYY-MM-DD'
    hora_retirada = data.get('hora')  # int

    pedido = Pedido.query.filter_by(numero=numero).first()
    if not pedido:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    if pedido.status != 'paid':
        return jsonify({'erro': 'Pagamento não confirmado'}), 400

    data_obj = date.fromisoformat(data_retirada)

    # Verifica disponibilidade
    config = get_config_agenda()
    ocupados = Agendamento.query.filter_by(
        data_retirada=data_obj,
        hora_retirada=hora_retirada
    ).filter(Agendamento.status != 'cancelado').count()

    agendamento_existente = Agendamento.query.filter_by(pedido_id=pedido.id).first()
    if agendamento_existente:
        # Desconta o próprio agendamento na contagem se estiver remarcando
        if agendamento_existente.data_retirada == data_obj and agendamento_existente.hora_retirada == hora_retirada:
            return jsonify({'erro': 'Você já está agendado neste horário'}), 400
        ocupados_reais = ocupados - (1 if agendamento_existente.status != 'cancelado' and
                                     agendamento_existente.data_retirada == data_obj and
                                     agendamento_existente.hora_retirada == hora_retirada else 0)
        if ocupados_reais >= config.max_por_horario:
            return jsonify({'erro': 'Horário indisponível'}), 409
        agendamento_existente.data_retirada = data_obj
        agendamento_existente.hora_retirada = hora_retirada
        agendamento_existente.status = 'remarcado'
        agendamento_existente.atualizado_em = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True, 'remarcado': True, 'label': f"{data_obj.strftime('%d/%m/%Y')} às {hora_retirada:02d}:00"})

    if ocupados >= config.max_por_horario:
        return jsonify({'erro': 'Horário indisponível'}), 409

    agendamento = Agendamento(
        pedido_id=pedido.id,
        data_retirada=data_obj,
        hora_retirada=hora_retirada
    )
    db.session.add(agendamento)
    db.session.commit()
    return jsonify({'ok': True, 'remarcado': False, 'label': f"{data_obj.strftime('%d/%m/%Y')} às {hora_retirada:02d}:00"})

@app.route('/api/horarios-disponiveis')
def api_horarios_disponiveis():
    """Retorna slots disponíveis (usado pelo frontend da página de agendamento)."""
    numero = request.args.get('numero')
    pedido = Pedido.query.filter_by(numero=numero).first()
    if not pedido or pedido.status != 'paid':
        return jsonify([])
    slots = horarios_disponiveis(pedido_pago_em=pedido.criado_em)
    return jsonify(slots)

# ─── SORTEIO PÚBLICO ─────────────────────────────────────────────

@app.route('/sorteio')
def sorteio_page():
    s = Sorteio.query.filter_by(ativo=True).first()
    numeros_reservados = []
    if s:
        numeros_reservados = [n.numero for n in s.numeros]
    return render_template('sorteio.html', sorteio=s, numeros_reservados=numeros_reservados)

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
        'services': '1,2,17'
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

    # ── Sorteio: atribuir número automático ao comprador ──
    sorteio_ativo = Sorteio.query.filter_by(ativo=True).first()
    if sorteio_ativo:
        numeros_usados = [n.numero for n in sorteio_ativo.numeros]
        todos = list(range(1, sorteio_ativo.total_numeros + 1))
        disponiveis = [n for n in todos if n not in numeros_usados]
        if disponiveis:
            import random
            numero_sorteado = random.choice(disponiveis)
            novo_numero = NumeroSorteio(
                sorteio_id=sorteio_ativo.id,
                numero=numero_sorteado,
                nome_participante=data['nome'],
                telefone=data.get('telefone', ''),
                pedido_id=pedido.id
            )
            db.session.add(novo_numero)

    db.session.commit()

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
            status_mp = payment.get('status')

            if pedido_id:
                pedido = Pedido.query.get(pedido_id)
                if pedido:
                    pedido.mp_payment_id = str(resource_id)
                    if status_mp == 'approved' and pedido.status != 'paid':
                        pedido.status = 'paid'
                        db.session.commit()
                        email_pedido_confirmado(pedido, pedido.itens)
                        email_novo_pedido_admin(pedido, pedido.itens)
                    elif status_mp in ('rejected', 'cancelled'):
                        pedido.status = 'cancelled'
                    db.session.commit()

    return jsonify({'status': 'ok'}), 200

# ─── ADMIN: LOGIN ─────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if admin_logado():
        return redirect(url_for('admin'))

    erro = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        from sqlalchemy import text
        row = db.session.execute(
            text("SELECT id, senha_hash, ativo FROM admins WHERE email = :email"),
            {'email': email}
        ).mappings().fetchone()

        if row and row['ativo'] and bcrypt.checkpw(senha.encode(), row['senha_hash'].encode()):
            session['admin_id'] = str(row['id'])
            session.permanent = True
            return redirect(url_for('admin'))
        else:
            erro = 'E-mail ou senha incorretos.'

    return render_template('admin_login.html', erro=erro)

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

# ─── ADMIN: PAINEL ────────────────────────────────────────────────

@app.route('/admin/pedido/<pedido_id>/rastreio', methods=['POST'])
def atualizar_rastreio(pedido_id):
    if not admin_logado():
        abort(401)
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.codigo_rastreio = request.json.get('codigo')
    pedido.status = 'enviado'
    db.session.commit()
    email_pedido_enviado(pedido)
    return jsonify({'ok': True})

@app.route('/admin/pedido/<pedido_id>/status', methods=['POST'])
def atualizar_status(pedido_id):
    if not admin_logado():
        abort(401)
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.status = request.json.get('status')
    db.session.commit()
    return jsonify({'ok': True})

# ─── ADMIN: PRODUTOS ─────────────────────────────────────────────

@app.route('/admin/produto', methods=['POST'])
def criar_produto():
    if not admin_logado(): abort(401)
    d = request.json
    p = Produto(
        nome=d['nome'], slug=d['slug'],
        descricao=d.get('descricao', ''),
        itens=json.dumps([i.strip() for i in d.get('itens', '').split('\n') if i.strip()]),
        preco=Decimal(str(d['preco'])),
        imagem=d.get('imagem', ''),
        peso=float(d.get('peso', 1)),
        altura=float(d.get('altura', 20)),
        largura=float(d.get('largura', 20)),
        comprimento=float(d.get('comprimento', 20)),
        ativo=True
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok': True, 'id': p.id})

@app.route('/admin/produto/<produto_id>', methods=['POST'])
def editar_produto(produto_id):
    if not admin_logado(): abort(401)
    p = Produto.query.get_or_404(produto_id)
    d = request.json
    p.nome = d['nome']
    p.slug = d['slug']
    p.descricao = d.get('descricao', '')
    p.itens = json.dumps([i.strip() for i in d.get('itens', '').split('\n') if i.strip()])
    p.preco = Decimal(str(d['preco']))
    p.imagem = d.get('imagem', '')
    p.peso = float(d.get('peso', 1))
    p.altura = float(d.get('altura', 20))
    p.largura = float(d.get('largura', 20))
    p.comprimento = float(d.get('comprimento', 20))
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/produto/<produto_id>', methods=['DELETE'])
def excluir_produto(produto_id):
    if not admin_logado(): abort(401)
    p = Produto.query.get_or_404(produto_id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/produto/<produto_id>/toggle', methods=['POST'])
def toggle_produto(produto_id):
    if not admin_logado(): abort(401)
    p = Produto.query.get_or_404(produto_id)
    p.ativo = request.json.get('ativo', not p.ativo)
    db.session.commit()
    return jsonify({'ok': True})

# ─── ADMIN: SORTEIO ──────────────────────────────────────────────

@app.route('/admin/sorteio', methods=['POST'])
def admin_criar_sorteio():
    if not admin_logado(): abort(401)
    d = request.json
    # Desativa sorteios anteriores
    Sorteio.query.update({'ativo': False})
    s = Sorteio(
        titulo=d['titulo'],
        descricao=d.get('descricao', ''),
        imagem=d.get('imagem', ''),
        valor_numero=Decimal(str(d.get('valor_numero', 10))),
        total_numeros=int(d.get('total_numeros', 50)),
        data_sorteio=datetime.fromisoformat(d['data_sorteio']) if d.get('data_sorteio') else None,
        ativo=True
    )
    db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True, 'id': s.id})

@app.route('/admin/sorteio/<sorteio_id>', methods=['POST'])
def admin_editar_sorteio(sorteio_id):
    if not admin_logado(): abort(401)
    s = Sorteio.query.get_or_404(sorteio_id)
    d = request.json
    s.titulo = d.get('titulo', s.titulo)
    s.descricao = d.get('descricao', s.descricao)
    s.imagem = d.get('imagem', s.imagem)
    s.valor_numero = Decimal(str(d.get('valor_numero', s.valor_numero)))
    s.total_numeros = int(d.get('total_numeros', s.total_numeros))
    if d.get('data_sorteio'):
        s.data_sorteio = datetime.fromisoformat(d['data_sorteio'])
    s.ativo = d.get('ativo', s.ativo)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/sorteio/<sorteio_id>/numero', methods=['POST'])
def admin_reservar_numero(sorteio_id):
    if not admin_logado(): abort(401)
    d = request.json
    # Verifica se número já está reservado
    existe = NumeroSorteio.query.filter_by(sorteio_id=sorteio_id, numero=d['numero']).first()
    if existe:
        return jsonify({'erro': 'Número já reservado'}), 400
    n = NumeroSorteio(
        sorteio_id=sorteio_id,
        numero=d['numero'],
        nome_participante=d.get('nome'),
        telefone=d.get('telefone'),
        pedido_id=d.get('pedido_id')
    )
    db.session.add(n)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/sorteio/<sorteio_id>/numero/<int:numero>', methods=['DELETE'])
def admin_remover_numero(sorteio_id, numero):
    if not admin_logado(): abort(401)
    n = NumeroSorteio.query.filter_by(sorteio_id=sorteio_id, numero=numero).first_or_404()
    db.session.delete(n)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/sorteio/<sorteio_id>/numeros')
def admin_listar_numeros(sorteio_id):
    if not admin_logado(): abort(401)
    s = Sorteio.query.get_or_404(sorteio_id)
    numeros = [{
        'numero': n.numero,
        'nome': n.nome_participante,
        'telefone': n.telefone,
        'pedido_id': n.pedido_id,
        'reservado_em': n.reservado_em.isoformat() if n.reservado_em else ''
    } for n in s.numeros]
    return jsonify(numeros)

# ─── ADMIN: AGENDA ────────────────────────────────────────────────

@app.route('/admin/agenda')
def admin_agenda():
    """Retorna todos os agendamentos dos próximos 14 dias para o admin."""
    if not admin_logado(): abort(401)
    ate = date.today() + timedelta(days=14)
    agendamentos = Agendamento.query.filter(
        Agendamento.data_retirada >= date.today(),
        Agendamento.data_retirada <= ate
    ).order_by(Agendamento.data_retirada, Agendamento.hora_retirada).all()

    resultado = []
    for a in agendamentos:
        pedido = Pedido.query.get(a.pedido_id)
        resultado.append({
            'id': a.id,
            'pedido_numero': pedido.numero if pedido else '',
            'pedido_nome': pedido.nome if pedido else '',
            'pedido_telefone': pedido.telefone if pedido else '',
            'data': a.data_retirada.isoformat(),
            'hora': a.hora_retirada,
            'label': f"{a.data_retirada.strftime('%d/%m/%Y')} às {a.hora_retirada:02d}:00",
            'status': a.status
        })
    return jsonify(resultado)

@app.route('/admin/agenda/config', methods=['GET'])
def admin_get_config_agenda():
    if not admin_logado(): abort(401)
    config = get_config_agenda()
    return jsonify({
        'hora_abertura': config.hora_abertura,
        'hora_fechamento': config.hora_fechamento,
        'minutos_preparo': config.minutos_preparo,
        'max_por_horario': config.max_por_horario,
        'dias_semana': config.dias_semana
    })

@app.route('/admin/agenda/config', methods=['POST'])
def admin_salvar_config_agenda():
    if not admin_logado(): abort(401)
    d = request.json
    config = get_config_agenda()
    config.hora_abertura = int(d.get('hora_abertura', config.hora_abertura))
    config.hora_fechamento = int(d.get('hora_fechamento', config.hora_fechamento))
    config.minutos_preparo = int(d.get('minutos_preparo', config.minutos_preparo))
    config.max_por_horario = int(d.get('max_por_horario', config.max_por_horario))
    config.dias_semana = d.get('dias_semana', config.dias_semana)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/agenda/bloqueio', methods=['POST'])
def admin_criar_bloqueio():
    if not admin_logado(): abort(401)
    d = request.json
    b = BloqueioHorario(
        data=date.fromisoformat(d['data']),
        hora_inicio=d.get('hora_inicio'),  # None = dia inteiro
        hora_fim=d.get('hora_fim'),
        motivo=d.get('motivo', '')
    )
    db.session.add(b)
    db.session.commit()
    return jsonify({'ok': True, 'id': b.id})

@app.route('/admin/agenda/bloqueio/<int:bloqueio_id>', methods=['DELETE'])
def admin_remover_bloqueio(bloqueio_id):
    if not admin_logado(): abort(401)
    b = BloqueioHorario.query.get_or_404(bloqueio_id)
    db.session.delete(b)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/agenda/bloqueios')
def admin_listar_bloqueios():
    if not admin_logado(): abort(401)
    ate = date.today() + timedelta(days=60)
    bloqueios = BloqueioHorario.query.filter(
        BloqueioHorario.data >= date.today(),
        BloqueioHorario.data <= ate
    ).order_by(BloqueioHorario.data).all()
    return jsonify([{
        'id': b.id,
        'data': b.data.isoformat(),
        'hora_inicio': b.hora_inicio,
        'hora_fim': b.hora_fim,
        'motivo': b.motivo or '',
        'label': f"{b.data.strftime('%d/%m/%Y')}" + (f" {b.hora_inicio:02d}h–{b.hora_fim:02d}h" if b.hora_inicio is not None else ' (dia inteiro)')
    } for b in bloqueios])

def pedido_to_dict(p):
    agendamento = None
    if p.agendamento:
        agendamento = {
            'data': p.agendamento.data_retirada.isoformat(),
            'hora': p.agendamento.hora_retirada,
            'label': f"{p.agendamento.data_retirada.strftime('%d/%m/%Y')} às {p.agendamento.hora_retirada:02d}:00",
            'status': p.agendamento.status
        }
    return {
        'id': str(p.id),
        'numero': p.numero,
        'nome': p.nome,
        'email': p.email,
        'telefone': p.telefone or '',
        'tipo_entrega': p.tipo_entrega,
        'cep': p.cep or '',
        'endereco': p.endereco or '',
        'servico_frete': p.servico_frete or '',
        'valor_frete': float(p.valor_frete) if p.valor_frete else 0,
        'valor_total': float(p.valor_total),
        'mensagem': p.mensagem or '',
        'status': p.status,
        'codigo_rastreio': p.codigo_rastreio or '',
        'mp_payment_id': p.mp_payment_id or '',
        'criado_em': p.criado_em.isoformat() if p.criado_em else '',
        'agendamento': agendamento,
        'itens': [
            {
                'nome_produto': i.nome_produto,
                'preco_unitario': float(i.preco_unitario),
                'quantidade': i.quantidade,
            }
            for i in p.itens
        ],
    }

@app.route('/admin')
def admin():
    if not admin_logado(): return redirect(url_for('admin_login'))
    pedidos = Pedido.query.order_by(Pedido.criado_em.desc()).limit(100).all()
    produtos = Produto.query.order_by(Produto.id).all()
    sorteios = Sorteio.query.order_by(Sorteio.criado_em.desc()).all()
    sorteio_ativo = Sorteio.query.filter_by(ativo=True).first()
    pedidos_json = [pedido_to_dict(p) for p in pedidos]

    # Agendamentos dos próximos 14 dias para a aba Agenda
    ate = date.today() + timedelta(days=14)
    agendamentos_proximos = Agendamento.query.filter(
        Agendamento.data_retirada >= date.today(),
        Agendamento.data_retirada <= ate
    ).order_by(Agendamento.data_retirada, Agendamento.hora_retirada).all()
    config_agenda = get_config_agenda()

    return render_template('admin.html',
        pedidos=pedidos,
        produtos=produtos,
        sorteios=sorteios,
        sorteio_ativo=sorteio_ativo,
        pedidos_json=pedidos_json,
        agendamentos_proximos=agendamentos_proximos,
        config_agenda=config_agenda
    )

# ─── INICIALIZAÇÃO ────────────────────────────────────────────────

with app.app_context():
    db.create_all()
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
