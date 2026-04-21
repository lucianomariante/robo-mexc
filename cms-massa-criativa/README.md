# CMS Massa Criativa

Projeto novo e independente para você versionar em um repositório Git separado chamado **CMS Massa Criativa**.

## Recursos
- Painel administrativo moderno com Bootstrap.
- Setup inicial de administrador.
- Multi-site (um CMS para vários clientes).
- CRUD de páginas com status rascunho/publicado.
- API pública para qualquer frontend consumir.

## Rodando localmente
```bash
cd cms-massa-criativa
pip install -r requirements.txt
python app.py
```

Abra no navegador:
- Setup inicial: `http://localhost:8080/setup`
- Login: `http://localhost:8080/login`

## Endpoint para plugar no site do cliente
```text
GET /api/v1/sites/<site_slug>/pages/<page_slug>
```

Exemplo:
```bash
curl http://localhost:8080/api/v1/sites/cliente-x/pages/home
```

## Criando o repo Git separado
Dentro de `cms-massa-criativa/` execute:
```bash
git init
git add .
git commit -m "feat: bootstrap CMS Massa Criativa"
```
Depois conecte ao remoto (GitHub/GitLab):
```bash
git remote add origin <url-do-repo>
git branch -M main
git push -u origin main
```
