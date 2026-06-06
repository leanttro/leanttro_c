from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

def gen_uuid():
    return str(uuid.uuid4())

# ─── CATEGORIA ────────────────────────────────────────────────────

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id          = db.Column(db.String, primary_key=True, default=gen_uuid)
    nome        = db.Column(db.String(200), nullable=False)   # ex: Dia dos Pais
    slug        = db.Column(db.String(200), unique=True, nullable=False)  # ex: dia-dos-pais
    descricao   = db.Column(db.Text)                           # usado na meta description da página
    imagem      = db.Column(db.String(500))                    # banner da categoria
    ativo       = db.Column(db.Boolean, default=True)
    ordem       = db.Column(db.Integer, default=0)             # ordem no carrossel/nav
    criado_em   = db.Column(db.DateTime, default=datetime.utcnow)

    produtos = db.relationship('Produto', backref='categoria', lazy=True)

# ─── PRODUTO ──────────────────────────────────────────────────────

class Produto(db.Model):
    __tablename__ = 'produtos'
    id          = db.Column(db.String, primary_key=True, default=gen_uuid)
    nome        = db.Column(db.String(200), nullable=False)
    slug        = db.Column(db.String(200), unique=True, nullable=False)
    descricao   = db.Column(db.Text)
    itens       = db.Column(db.Text)   # JSON string com lista de itens
    preco       = db.Column(db.Numeric(10, 2), nullable=False)
    imagem      = db.Column(db.String(500))
    peso        = db.Column(db.Float, default=2.0)
    altura      = db.Column(db.Integer, default=20)
    largura     = db.Column(db.Integer, default=30)
    comprimento = db.Column(db.Integer, default=30)
    ativo       = db.Column(db.Boolean, default=True)
    prazo_quantidade = db.Column(db.Integer, default=1)      # ex: 4
    prazo_unidade    = db.Column(db.String(20), default='dias úteis')  # horas | dias | dias úteis
    criado_em   = db.Column(db.DateTime, default=datetime.utcnow)

    categoria_id = db.Column(db.String, db.ForeignKey('categorias.id'), nullable=True)

# ─── PEDIDO ───────────────────────────────────────────────────────

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id          = db.Column(db.String, primary_key=True, default=gen_uuid)
    numero      = db.Column(db.String(20), unique=True)  # ex: CP-20240612-001

    # Cliente
    nome        = db.Column(db.String(200), nullable=False)
    email       = db.Column(db.String(200), nullable=False)
    telefone    = db.Column(db.String(20))

    # Entrega
    tipo_entrega  = db.Column(db.String(20), default='retirada')  # retirada | envio
    cep           = db.Column(db.String(10))
    endereco      = db.Column(db.String(300))
    servico_frete = db.Column(db.String(100))
    valor_frete   = db.Column(db.Numeric(10, 2), default=0)

    # Pagamento
    status           = db.Column(db.String(30), default='pending')  # pending | paid | cancelled | refunded
    mp_payment_id    = db.Column(db.String(100))
    mp_preference_id = db.Column(db.String(200))
    valor_total      = db.Column(db.Numeric(10, 2))

    # Mensagem personalizada
    mensagem = db.Column(db.Text)

    # Rastreio
    codigo_rastreio = db.Column(db.String(50))

    criado_em    = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    itens        = db.relationship('ItemPedido', backref='pedido', lazy=True)
    agendamento  = db.relationship('Agendamento', backref='pedido', lazy=True, uselist=False)

class ItemPedido(db.Model):
    __tablename__ = 'itens_pedido'
    id            = db.Column(db.Integer, primary_key=True)
    pedido_id     = db.Column(db.String, db.ForeignKey('pedidos.id'), nullable=False)
    produto_id    = db.Column(db.String, db.ForeignKey('produtos.id'))
    nome_produto  = db.Column(db.String(200))
    preco_unitario = db.Column(db.Numeric(10, 2))
    quantidade    = db.Column(db.Integer, default=1)

# ─── SORTEIO ─────────────────────────────────────────────────────

class Sorteio(db.Model):
    __tablename__ = 'sorteios'
    id            = db.Column(db.String, primary_key=True, default=gen_uuid)
    titulo        = db.Column(db.String(200), nullable=False)
    descricao     = db.Column(db.Text)
    imagem        = db.Column(db.String(500))
    valor_numero  = db.Column(db.Numeric(10, 2), default=10.00)
    total_numeros = db.Column(db.Integer, default=50)
    data_sorteio  = db.Column(db.DateTime)
    ativo         = db.Column(db.Boolean, default=True)
    criado_em     = db.Column(db.DateTime, default=datetime.utcnow)

    numeros = db.relationship('NumeroSorteio', backref='sorteio', lazy=True)

class NumeroSorteio(db.Model):
    __tablename__ = 'numeros_sorteio'
    id                = db.Column(db.Integer, primary_key=True)
    sorteio_id        = db.Column(db.String, db.ForeignKey('sorteios.id'), nullable=False)
    numero            = db.Column(db.Integer, nullable=False)
    nome_participante = db.Column(db.String(200))
    telefone          = db.Column(db.String(20))
    pedido_id         = db.Column(db.String, db.ForeignKey('pedidos.id'), nullable=True)
    reservado_em      = db.Column(db.DateTime, default=datetime.utcnow)
    status            = db.Column(db.String(20), default='confirmado')  # pendente | confirmado

# ─── AGENDAMENTO ─────────────────────────────────────────────────

class ConfigAgenda(db.Model):
    __tablename__ = 'config_agenda'
    id              = db.Column(db.Integer, primary_key=True)
    hora_abertura   = db.Column(db.Integer, default=7)
    hora_fechamento = db.Column(db.Integer, default=21)
    minutos_preparo = db.Column(db.Integer, default=180)
    max_por_horario = db.Column(db.Integer, default=1)
    dias_semana     = db.Column(db.String(20), default='1,2,3,4,5,6')

class BloqueioHorario(db.Model):
    __tablename__ = 'bloqueios_horario'
    id          = db.Column(db.Integer, primary_key=True)
    data        = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.Integer, nullable=True)
    hora_fim    = db.Column(db.Integer, nullable=True)
    motivo      = db.Column(db.String(200))
    criado_em   = db.Column(db.DateTime, default=datetime.utcnow)

class Agendamento(db.Model):
    __tablename__ = 'agendamentos'
    id            = db.Column(db.String, primary_key=True, default=gen_uuid)
    pedido_id     = db.Column(db.String, db.ForeignKey('pedidos.id'), nullable=False, unique=True)
    data_retirada = db.Column(db.Date, nullable=False)
    hora_retirada = db.Column(db.Integer, nullable=False)
    status        = db.Column(db.String(20), default='confirmado')  # confirmado | remarcado | cancelado
    criado_em     = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
