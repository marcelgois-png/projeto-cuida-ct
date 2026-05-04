# Checklist de Producao

Este projeto e uma aplicacao Django servida por Gunicorn, com arquivos estaticos via WhiteNoise e banco MySQL 8.

## Variaveis obrigatorias

Configure um `.env` real no servidor, sem versionar o arquivo:

```env
SECRET_KEY=gere-uma-chave-longa-e-aleatoria
DEBUG=False
ALLOWED_HOSTS=seu-dominio.com,www.seu-dominio.com
CSRF_TRUSTED_ORIGINS=https://seu-dominio.com,https://www.seu-dominio.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
USE_X_FORWARDED_PROTO=True
DJANGO_USE_SQLITE=False
MYSQL_DB=ct_sinfra
MYSQL_USER=ct_sinfra
MYSQL_PASSWORD=troque-esta-senha
MYSQL_ROOT_PASSWORD=troque-esta-senha-root
MYSQL_HOST=db
MYSQL_PORT=3306
GROQ_API_KEY=
```

Preencha `GROQ_API_KEY` somente se a extracao de orcamento por IA estiver ativa.

## Primeiro deploy

1. Gere e revise o `.env` de producao.
2. Suba o build:

```bash
docker compose up --build -d
```

3. Confirme que as migracoes rodaram:

```bash
docker compose logs web
```

4. Crie o usuario administrativo, se necessario:

```bash
docker compose exec web python manage.py createsuperuser
```

## Validacoes antes de publicar

Rode localmente ou no CI:

```bash
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput --dry-run
python manage.py test apps.tracker apps.processos --settings=ct_sinfra.settings_test
```

Para maior seguranca, teste tambem uma migracao completa em um MySQL vazio antes do deploy definitivo.

## Arquivos estaticos e midia

Arquivos estaticos sao coletados para `staticfiles/` e servidos pelo WhiteNoise.

Arquivos de midia em `media/` precisam de persistencia propria em producao. Use volume persistente, Nginx servindo a pasta, ou armazenamento externo como S3/MinIO.

## Backups

Antes de qualquer atualizacao:

```bash
docker compose exec db mysqldump -u root -p ct_sinfra > backup_ct_sinfra.sql
```

Tambem preserve a pasta/volume de midia.

## Observacoes

- Nao use `DEBUG=True` em producao.
- Nao versionar `.env`, `db.sqlite3`, `media/`, `staticfiles/`, `outputs/` ou arquivos gerados.
- O proxy reverso deve encerrar HTTPS e encaminhar `X-Forwarded-Proto: https`.
