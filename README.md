# IR Premium SaaS

Sistema web para contabilidades recolherem documentos do Imposto de Renda por link público.

## Rodar local
```bash
pip install -r requirements.txt
python app.py
```
Acesse: http://127.0.0.1:5000

## Deploy Render
Build Command:
```bash
pip install --upgrade pip && pip install -r requirements.txt
```
Start Command:
```bash
python -m gunicorn app:app --bind 0.0.0.0:$PORT
```

## Estrutura obrigatória
- `app.py` na raiz
- HTML dentro de `templates/`
- CSS dentro de `static/`
