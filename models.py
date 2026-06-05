from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

def gen_uuid():
    return str(uuid.uuid4())

class Produto(db.Model):
    __tablename__ = 'produtos'
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    nome = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    descricao = db.Column(db.Text)
    itens = db.Column(db.Text)  # JSON string com lista de itens
    preco = db.Column(db.Numeric(10, 2), nullable=False)
    imagem = db.Column(db.String(500))
    peso = db.Column(db.Float, default=2.0)
    altura = db.Column(db.Integer, default=20)
    largura = db.Column(db.Integer, default=30)
    comprimento = db.Column(db.Integer, default=30)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    numero = db.Column(db.String(20), unique=True)  # ex: CP-20240612-001

    # Cliente
    nome = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    telefone = db.Column(db.String(20))

    # Entrega
    tipo_entrega = db.Column(db.String(20), default='retirada')  # retirada | envio
    cep = db.Column(db.String(10))
    endereco = db.Column(db.String(300))
    servico_frete = db.Column(db.String(100))
    valor_frete = db.Column(db.Numeric(10, 2), default=0)

    # Pagamento
    status = db.Column(db.String(30), default='pending')  # pending | paid | cancelled | refunded
    mp_payment_id = db.Column(db.String(100))
    mp_preference_id = db.Column(db.String(200))
    valor_total = db.Column(db.Numeric(10, 2))

    # Mensagem personalizada
    mensagem = db.Column(db.Text)

    # Rastreio
    codigo_rastreio = db.Column(db.String(50))

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    itens = db.relationship('ItemPedido', backref='pedido', lazy=True)

class ItemPedido(db.Model):
    __tablename__ = 'itens_pedido'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.String, db.ForeignKey('pedidos.id'), nullable=False)
    produto_id = db.Column(db.String, db.ForeignKey('produtos.id'))
    nome_produto = db.Column(db.String(200))
    preco_unitario = db.Column(db.Numeric(10, 2))
    quantidade = db.Column(db.Integer, default=1)

# ─── SORTEIO ─────────────────────────────────────────────────────

class Sorteio(db.Model):
    __tablename__ = 'sorteios'
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    imagem = db.Column(db.String(500))
    valor_numero = db.Column(db.Numeric(10, 2), default=10.00)
    total_numeros = db.Column(db.Integer, default=50)
    data_sorteio = db.Column(db.DateTime)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    numeros = db.relationship('NumeroSorteio', backref='sorteio', lazy=True)

class NumeroSorteio(db.Model):
    __tablename__ = 'numeros_sorteio'
    id = db.Column(db.Integer, primary_key=True)
    sorteio_id = db.Column(db.String, db.ForeignKey('sorteios.id'), nullable=False)
    numero = db.Column(db.Integer, nullable=False)
    nome_participante = db.Column(db.String(200))
    telefone = db.Column(db.String(20))
    pedido_id = db.Column(db.String, db.ForeignKey('pedidos.id'), nullable=True)  # se veio de compra
    reservado_em = db.Column(db.DateTime, default=datetime.utcnow)
