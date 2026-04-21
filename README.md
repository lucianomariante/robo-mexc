# Robo MEXC + CMS Plugável

Este repositório agora contém:

- **Bot MEXC** (arquivos originais para integração com websocket protobuf).
- **CMS Plugável** em Flask para entregar junto com sites de clientes.

## 1) Bot MEXC

As definições `.proto` de [mexcdevelop/websocket-proto](https://github.com/mexcdevelop/websocket-proto)
estão em `protos/` e os módulos gerados em `mexc_pb/`.

Para regenerar:

```bash
protoc --proto_path=protos --python_out=mexc_pb protos/*.proto
```

Executar:

```bash
pip install -r requirements.txt
python crypto_bot_mexc.py
```

## 2) CMS Plugável (novo)

### O que ele resolve

Você pode gerenciar conteúdo de **múltiplos sites/clientes** sem que o cliente precise programar.

Funcionalidades:

- Login de administrador.
- Cadastro de múltiplos sites (cada um com `slug`).
- CRUD completo de páginas (rascunho/publicado).
- API pública para consumo em qualquer site/frontend.

### Instalação

```bash
pip install -r requirements.txt
python cms_app.py
```

Na primeira execução, abra:

- `http://localhost:8000/setup` para criar o admin.

Depois, use:

- `http://localhost:8000/login` para entrar no painel.

### API para plugar em qualquer site

Endpoint:

```text
GET /api/sites/<site_slug>/pages/<page_slug>
```

Retorna JSON com título, conteúdo e metadados da página **publicada**.

Exemplo:

```bash
curl http://localhost:8000/api/sites/meu-cliente/pages/home
```

### Exemplo de integração rápida (JavaScript)

```html
<script>
  async function carregarPagina() {
    const res = await fetch('http://localhost:8000/api/sites/meu-cliente/pages/home');
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('titulo').textContent = data.page.title;
    document.getElementById('conteudo').innerHTML = data.page.content;
  }
  carregarPagina();
</script>
```

> Para produção: configure `CMS_SECRET_KEY` e execute atrás de um servidor web (Nginx/Caddy) com HTTPS.
