# Bot de Boas-vindas X86 Team

Bot para enviar o banner e a mensagem de boas-vindas em formato de citação no tópico **Geral** de um grupo do Telegram.

## Configuração

1. Crie o bot pelo [@BotFather](https://t.me/BotFather) usando `/newbot` e copie o token.
2. Adicione o bot ao grupo e dê permissão para enviar mensagens e fotos. De preferência, torne-o administrador.
3. Ative os tópicos no grupo. O tópico Geral usa o ID `1` por padrão.
4. Crie o arquivo `.env` a partir de `.env.example` e informe o token.

## Execução

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

O arquivo `photo_2026-08-28_02-08-41.jpg` já está configurado como banner. Para usar outro arquivo, altere `WELCOME_IMAGE` no `.env`.

Se o grupo usar um ID diferente para o tópico Geral, altere `GENERAL_TOPIC_ID` no `.env`.

## Deploy no Render

O arquivo `render.yaml` configura o bot como **Background Worker**, que é o tipo correto para o polling do Telegram.

1. Revogue o token exposto no `@BotFather` e gere um novo.
2. Publique esta pasta em um repositório GitHub privado.
3. No Render, selecione **New > Blueprint** e conecte o repositório.
4. Quando solicitado, preencha `TELEGRAM_BOT_TOKEN` com o novo token diretamente no Render.
5. Faça o deploy e mantenha o worker ativo.

Não coloque o token no `render.yaml`, no GitHub ou em mensagens. O `sync: false` faz o Render tratar `TELEGRAM_BOT_TOKEN` como segredo.
