# Entrega para Equipe de TI

Este documento orienta a implantacao do Sistema CT -> SINFRA em ambiente de producao. A configuracao de servidor, Docker, banco, HTTPS e backups deve ser conduzida pela equipe de TI.

## Resumo da aplicacao

- Aplicacao web Django.
- Servidor de aplicacao: Gunicorn.
- Banco de dados: MySQL 8.
- Arquivos estaticos: WhiteNoise.
- Arquivos de midia: pasta `media/`, com necessidade de persistencia.
- Execucao recomendada: Docker Compose.

## O que deve ser providenciado pela TI

1. Servidor Linux com Docker e Docker Compose instalados.
2. Dominio ou subdominio para acesso ao sistema.
3. HTTPS com certificado valido.
4. Proxy reverso, por exemplo Nginx, Apache ou proxy institucional.
5. Armazenamento persistente para banco MySQL.
6. Armazenamento persistente para arquivos de midia.
7. Rotina de backup do banco e dos arquivos de midia.
8. Politica de acesso ao servidor e usuarios administrativos.

## Variaveis de ambiente

Usar `.env.example` como base para criar o `.env` real no servidor.

Variaveis obrigatorias:

```env
SECRET_KEY=gerar-chave-longa-e-aleatoria
DEBUG=False
ALLOWED_HOSTS=dominio.institucional.br
CSRF_TRUSTED_ORIGINS=https://dominio.institucional.br
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
MYSQL_PASSWORD=definir-senha-segura
MYSQL_ROOT_PASSWORD=definir-senha-root-segura
MYSQL_HOST=db
MYSQL_PORT=3306
GROQ_API_KEY=
```

Observacoes:

- `SECRET_KEY` deve ser gerada pela TI, longa e aleatoria.
- `DEBUG` deve permanecer `False`.
- `ALLOWED_HOSTS` deve conter o dominio real.
- `CSRF_TRUSTED_ORIGINS` deve conter a URL HTTPS real.
- `GROQ_API_KEY` so precisa ser preenchida se a funcionalidade de extracao de orcamento por IA for usada.

## Comandos esperados

Na raiz do projeto:

```bash
docker compose up --build -d
```

O container web ja executa:

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn ct_sinfra.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

Para verificar logs:

```bash
docker compose logs web
docker compose logs db
```

Para criar o primeiro usuario administrador:

```bash
docker compose exec web python manage.py createsuperuser
```

## Validacoes antes de publicar

A equipe de TI deve validar:

```bash
docker compose config
docker compose up --build -d
docker compose logs web
docker compose exec web python manage.py check --deploy
```

Tambem e recomendado testar uma instalacao em banco MySQL vazio antes da publicacao definitiva.

## Proxy reverso e HTTPS

O proxy reverso deve:

- encaminhar requisicoes HTTPS para o container web na porta `8000`;
- enviar o cabecalho `X-Forwarded-Proto: https`;
- servir ou encaminhar arquivos de midia conforme estrategia definida;
- manter redirecionamento HTTP -> HTTPS.

## Arquivos de midia

O sistema usa `MEDIA_ROOT=media/`.

Esta pasta pode conter fotos de usuarios, anexos e arquivos de orcamento. Em producao, ela nao deve ficar apenas dentro de container descartavel.

Escolher uma das estrategias:

- volume persistente no servidor;
- pasta servida pelo Nginx/Apache;
- storage institucional;
- S3/MinIO ou equivalente.

## Backup

Backup minimo necessario:

1. Banco MySQL.
2. Pasta ou volume de midia.
3. Arquivo `.env` de producao, armazenado com seguranca.

Exemplo de dump manual:

```bash
docker compose exec db mysqldump -u root -p ct_sinfra > backup_ct_sinfra.sql
```

A TI deve definir periodicidade, retencao e teste de restauracao.

## Checklist de aceite

Antes de liberar para uso:

- [ ] Aplicacao sobe com `docker compose up --build -d`.
- [ ] `docker compose logs web` nao apresenta erro de migracao.
- [ ] `python manage.py check --deploy` passa no container web.
- [ ] Dominio HTTPS abre a pagina inicial.
- [ ] Login funciona.
- [ ] Usuario administrador foi criado.
- [ ] Importacao/teste basico de requisicoes funciona.
- [ ] Cadastro e consulta de processos funcionam.
- [ ] Pasta de midia esta persistente.
- [ ] Backup do banco esta configurado.
- [ ] Backup da midia esta configurado.
- [ ] Procedimento de restauracao foi documentado ou testado.

## Arquivos importantes

- `.env.example`: modelo de variaveis de ambiente.
- `docker-compose.yml`: orquestracao da aplicacao e do banco.
- `Dockerfile`: imagem da aplicacao.
- `docs/PRODUCAO.md`: checklist tecnico complementar.
- `requirements.txt`: dependencias Python.

## Contato funcional

Em caso de duvidas sobre regra de negocio, validar com a equipe do Centro de Tecnologia antes de alterar dados em producao.
