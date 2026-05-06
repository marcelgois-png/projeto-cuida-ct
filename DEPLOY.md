# Guia de Deploy — CT-SINFRA

Sistema web institucional do Centro de Tecnologia da UFPB para acompanhamento de requisições de manutenção junto à SINFRA.

**Responsável pelo código:** Direção do CT  
**Responsável pelo ambiente:** Equipe de TI do CT  
**Stack:** Python 3.13 · Django 5 · MySQL 8 · Docker

---

## Pré-requisitos no servidor

- Docker Engine 24+
- Docker Compose v2+
- Acesso à porta 8000 (ou outra definida no proxy reverso)
- Nginx ou similar atuando como proxy reverso (obrigatório para HTTPS)

---

## Primeira implantação

### 1. Obter o código

```bash
git clone <url-do-repositorio> /opt/ct-sinfra
cd /opt/ct-sinfra
```

### 2. Criar o arquivo de ambiente

```bash
cp .env.example .env
```

Edite `.env` e preencha **todos** os campos marcados abaixo. Não suba este arquivo para o repositório.

### 3. Subir os containers

```bash
docker compose up -d --build
```

### 4. Executar as migrações

```bash
docker compose exec web python manage.py migrate
```

### 5. Criar o usuário administrativo inicial

```bash
docker compose exec web python manage.py createsuperuser
```

### 6. Verificar que tudo está em pé

```bash
curl http://localhost:8000/health/
# Resposta esperada: {"status": "ok", "db": true}
```

---

## Variáveis de ambiente (arquivo `.env`)

| Variável | Obrigatória | Descrição | Exemplo |
|----------|-------------|-----------|---------|
| `SECRET_KEY` | **Sim** | Chave criptográfica da aplicação — gerar uma nova (ver abaixo) | `django-insecure-...` |
| `DEBUG` | **Sim** | Deve ser `False` em produção | `False` |
| `ALLOWED_HOSTS` | **Sim** | Domínio(s) do servidor, separados por vírgula | `ct.ufpb.br,www.ct.ufpb.br` |
| `CSRF_TRUSTED_ORIGINS` | **Sim** | Origens confiáveis para formulários, com protocolo | `https://ct.ufpb.br` |
| `MYSQL_DB` | **Sim** | Nome do banco de dados | `ct_sinfra` |
| `MYSQL_USER` | **Sim** | Usuário do banco | `ct_sinfra` |
| `MYSQL_PASSWORD` | **Sim** | Senha do banco — usar senha forte | `<senha-forte>` |
| `MYSQL_ROOT_PASSWORD` | **Sim** | Senha do root do MySQL | `<senha-forte>` |
| `MYSQL_HOST` | Não | Host do banco (padrão: `db`, nome do container) | `db` |
| `MYSQL_PORT` | Não | Porta do banco (padrão: `3306`) | `3306` |
| `SECURE_SSL_REDIRECT` | Não | Redirecionar HTTP para HTTPS (padrão: `True`) | `True` |
| `SESSION_COOKIE_SECURE` | Não | Cookie de sessão apenas via HTTPS (padrão: `True`) | `True` |
| `CSRF_COOKIE_SECURE` | Não | Cookie CSRF apenas via HTTPS (padrão: `True`) | `True` |
| `SECURE_HSTS_SECONDS` | Não | Duração do HSTS em segundos (padrão: `31536000`) | `31536000` |
| `USE_X_FORWARDED_PROTO` | Não | Ativar quando houver proxy reverso (padrão: `True`) | `True` |
| `SESSION_COOKIE_AGE` | Não | Expiração da sessão em segundos (padrão: `14400` = 4h) | `14400` |
| `DJANGO_LOG_LEVEL` | Não | Nível de log do Django (padrão: `WARNING`) | `WARNING` |
| `APP_LOG_LEVEL` | Não | Nível de log da aplicação (padrão: `INFO`) | `INFO` |

### Gerar uma SECRET_KEY segura

```bash
docker compose exec web python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copie o resultado e cole em `SECRET_KEY` no `.env`.

---

## Proxy reverso (Nginx)

O container expõe a porta `8000`. Configure o Nginx para fazer proxy reverso e terminar o SSL.

Exemplo mínimo de bloco `server`:

```nginx
server {
    listen 443 ssl;
    server_name ct.ufpb.br;

    ssl_certificate     /etc/ssl/certs/ct.ufpb.br.crt;
    ssl_certificate_key /etc/ssl/private/ct.ufpb.br.key;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        client_max_body_size 25M;
    }
}

server {
    listen 80;
    server_name ct.ufpb.br;
    return 301 https://$host$request_uri;
}
```

> **Atenção:** `client_max_body_size 25M` é necessário porque o sistema aceita uploads de planilhas de até 20 MB.

---

## Backup do banco de dados

### Backup manual

```bash
docker compose exec db mysqldump -u root -p ct_sinfra > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Backup automatizado (cron)

Adicionar ao crontab do servidor (`crontab -e`):

```cron
# Backup diário às 2h da manhã, retendo os últimos 30 dias
0 2 * * * docker compose -f /opt/ct-sinfra/docker-compose.yml exec -T db mysqldump -u root -p<MYSQL_ROOT_PASSWORD> ct_sinfra | gzip > /backups/ct-sinfra/$(date +\%Y\%m\%d).sql.gz && find /backups/ct-sinfra/ -name "*.sql.gz" -mtime +30 -delete
```

Criar o diretório de backups:

```bash
mkdir -p /backups/ct-sinfra
```

### Restaurar backup

```bash
gunzip < backup_20260101_020000.sql.gz | docker compose exec -T db mysql -u root -p ct_sinfra
```

---

## Monitoramento de saúde

A aplicação expõe um endpoint de health check:

```
GET /health/
```

Resposta em operação normal:
```json
{"status": "ok", "db": true}
```

Resposta com banco inacessível (HTTP 503):
```json
{"status": "degraded", "db": false}
```

Configure o monitorador (Zabbix, Nagios, UptimeRobot, etc.) para alertar se:
- O endpoint retornar status diferente de 200
- O campo `db` for `false`

---

## Atualizações

```bash
cd /opt/ct-sinfra

# 1. Baixar nova versão
git pull

# 2. Recriar containers com a nova imagem
docker compose up -d --build

# 3. Aplicar novas migrações (se houver)
docker compose exec web python manage.py migrate

# 4. Verificar saúde
curl http://localhost:8000/health/
```

### Rollback

Se a atualização causar problema:

```bash
# Voltar para o commit anterior
git log --oneline -5
git checkout <hash-do-commit-anterior>

# Recriar containers com a versão anterior
docker compose up -d --build
```

> **Atenção:** se a nova versão incluía migrações de banco, o rollback pode deixar o schema inconsistente. Nesse caso, restaurar o backup feito antes da atualização.

---

## Logs

Ver logs em tempo real:

```bash
# Todos os serviços
docker compose logs -f

# Apenas a aplicação
docker compose logs -f web

# Apenas o banco
docker compose logs -f db
```

Os logs seguem o formato:
```
TIMESTAMP  NÍVEL  MÓDULO  PID  MENSAGEM
```

---

## Comandos de manutenção

```bash
# Acessar o shell Django
docker compose exec web python manage.py shell

# Importar planilha pela linha de comando
docker compose exec web python manage.py importar_requisicoes /caminho/arquivo.xlsm

# Coletar arquivos estáticos manualmente
docker compose exec web python manage.py collectstatic --noinput

# Listar migrações pendentes
docker compose exec web python manage.py showmigrations
```

---

## Portas utilizadas

| Porta | Serviço | Exposição |
|-------|---------|-----------|
| 8000 | Aplicação Django (Gunicorn) | Local (via proxy Nginx) |
| 3306 | MySQL | Local (não expor externamente) |

> A porta 3306 do MySQL **não deve** ser exposta externamente. Acesso ao banco deve ser feito apenas via `docker compose exec`.

---

## Estrutura de volumes Docker

| Volume | Conteúdo | Criticidade |
|--------|----------|-------------|
| `mysql_data` | Dados do banco MySQL | **Crítico** — backup obrigatório |

Os arquivos estáticos são servidos pelo WhiteNoise diretamente da imagem (sem volume separado).

---

## Checklist de implantação

- [ ] `.env` criado com todas as variáveis obrigatórias
- [ ] `SECRET_KEY` gerada com o comando acima (nunca reutilizar a do `.env.example`)
- [ ] Senhas do MySQL diferentes das do `.env.example`
- [ ] `docker compose up -d --build` executado com sucesso
- [ ] Migrações aplicadas (`python manage.py migrate`)
- [ ] Superusuário criado
- [ ] `/health/` retorna `{"status": "ok", "db": true}`
- [ ] Nginx configurado com proxy reverso e SSL
- [ ] Cron de backup configurado
- [ ] Monitoramento do `/health/` configurado
