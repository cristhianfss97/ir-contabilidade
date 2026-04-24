
import os
import uuid
from datetime import datetime
from functools import wraps
from urllib.parse import quote

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'troque-essa-chave-em-producao')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'database.db')).replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024

db = SQLAlchemy(app)

class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    clientes = db.relationship('Cliente', backref='empresa', lazy=True, cascade='all, delete-orphan')

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    nome = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(160))
    telefone = db.Column(db.String(40))
    token = db.Column(db.String(80), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    documentos = db.relationship('Documento', backref='cliente', lazy=True, cascade='all, delete-orphan')

class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    nome = db.Column(db.String(160), nullable=False)
    obrigatorio = db.Column(db.Boolean, default=True)
    arquivo = db.Column(db.String(255))
    nome_original = db.Column(db.String(255))
    enviado_em = db.Column(db.DateTime)
    status = db.Column(db.String(30), default='pendente')

DOCUMENTOS_PADRAO = [
    'Documento de identificação com foto (RG ou CNH)',
    'CPF',
    'Comprovante de residência atualizado',
    'Informe de rendimentos da empresa',
    'Informe de rendimentos bancários',
    'Comprovantes de despesas médicas',
    'Comprovantes de despesas com educação',
    'Documentos de bens, veículos e imóveis',
    'Recibos de aluguel recebido ou pago',
    'Dados bancários para restituição'
]

@app.before_request
def criar_banco():
    db.create_all()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'empresa_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def empresa_atual():
    return Empresa.query.get(session.get('empresa_id'))

def allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf','png','jpg','jpeg','doc','docx','xls','xlsx'}

@app.route('/')
def home():
    if 'empresa_id' in session:
        return redirect(url_for('painel'))
    return redirect(url_for('login'))

@app.route('/cadastro', methods=['GET','POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        email = request.form.get('email','').strip().lower()
        senha = request.form.get('senha','')
        if not nome or not email or not senha:
            flash('Preencha todos os campos.', 'erro')
            return redirect(url_for('cadastro'))
        if Empresa.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'erro')
            return redirect(url_for('cadastro'))
        emp = Empresa(nome=nome, email=email, senha_hash=generate_password_hash(senha))
        db.session.add(emp); db.session.commit()
        flash('Cadastro criado com sucesso. Faça login.', 'ok')
        return redirect(url_for('login'))
    return render_template('auth.html', mode='cadastro')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        senha = request.form.get('senha','')
        emp = Empresa.query.filter_by(email=email).first()
        if emp and check_password_hash(emp.senha_hash, senha):
            session['empresa_id'] = emp.id
            return redirect(url_for('painel'))
        flash('Login ou senha inválidos.', 'erro')
    return render_template('auth.html', mode='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/painel')
@login_required
def painel():
    emp = empresa_atual()
    clientes = Cliente.query.filter_by(empresa_id=emp.id).order_by(Cliente.criado_em.desc()).all()
    total_clientes = len(clientes)
    total_docs = sum(len(c.documentos) for c in clientes)
    enviados = sum(1 for c in clientes for d in c.documentos if d.status == 'enviado')
    pendentes = total_docs - enviados
    percentual = int((enviados / total_docs) * 100) if total_docs else 0
    return render_template('painel.html', empresa=emp, clientes=clientes, total_clientes=total_clientes, total_docs=total_docs, enviados=enviados, pendentes=pendentes, percentual=percentual)

@app.route('/clientes/novo', methods=['POST'])
@login_required
def novo_cliente():
    emp = empresa_atual()
    cliente = Cliente(
        empresa_id=emp.id,
        nome=request.form.get('nome','').strip(),
        email=request.form.get('email','').strip(),
        telefone=request.form.get('telefone','').strip(),
        observacoes=request.form.get('observacoes','').strip(),
        token=str(uuid.uuid4())
    )
    if not cliente.nome:
        flash('Informe o nome do cliente.', 'erro')
        return redirect(url_for('painel'))
    db.session.add(cliente); db.session.flush()
    docs_txt = request.form.get('documentos','').strip()
    docs = [x.strip() for x in docs_txt.split('\n') if x.strip()] if docs_txt else DOCUMENTOS_PADRAO
    for nome in docs:
        db.session.add(Documento(cliente_id=cliente.id, nome=nome))
    db.session.commit()
    flash('Cliente criado e checklist gerado.', 'ok')
    return redirect(url_for('painel'))

@app.route('/cliente/<token>')
def portal_cliente(token):
    cliente = Cliente.query.filter_by(token=token).first_or_404()
    return render_template('portal.html', cliente=cliente)

@app.route('/cliente/<token>/upload/<int:doc_id>', methods=['POST'])
def upload_doc(token, doc_id):
    cliente = Cliente.query.filter_by(token=token).first_or_404()
    doc = Documento.query.filter_by(id=doc_id, cliente_id=cliente.id).first_or_404()
    arq = request.files.get('arquivo')
    if not arq or arq.filename == '':
        flash('Selecione um arquivo.', 'erro')
        return redirect(url_for('portal_cliente', token=token))
    if not allowed(arq.filename):
        flash('Formato inválido. Envie PDF, imagem, Word ou Excel.', 'erro')
        return redirect(url_for('portal_cliente', token=token))
    original = secure_filename(arq.filename)
    filename = f'{cliente.id}_{doc.id}_{uuid.uuid4().hex}_{original}'
    arq.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    doc.arquivo = filename
    doc.nome_original = original
    doc.status = 'enviado'
    doc.enviado_em = datetime.utcnow()
    db.session.commit()
    flash('Documento enviado com sucesso.', 'ok')
    return redirect(url_for('portal_cliente', token=token))

@app.route('/uploads/<path:filename>')
@login_required
def arquivo(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/cliente/<int:cliente_id>/excluir', methods=['POST'])
@login_required
def excluir_cliente(cliente_id):
    emp = empresa_atual()
    cliente = Cliente.query.filter_by(id=cliente_id, empresa_id=emp.id).first_or_404()
    db.session.delete(cliente); db.session.commit()
    flash('Cliente removido.', 'ok')
    return redirect(url_for('painel'))

@app.template_filter('whatsapp')
def whatsapp_link(cliente):
    base = request.url_root.rstrip('/')
    link = f'{base}/cliente/{cliente.token}'
    msg = f'Olá, {cliente.nome}! Segue seu link para envio dos documentos do Imposto de Renda: {link}'
    numero = ''.join(ch for ch in (cliente.telefone or '') if ch.isdigit())
    if numero and not numero.startswith('55'):
        numero = '55' + numero
    return f'https://wa.me/{numero}?text={quote(msg)}' if numero else f'https://wa.me/?text={quote(msg)}'

if __name__ == '__main__':
    app.run(debug=True)
