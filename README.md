# Sistema CT -> SINFRA

Sistema web institucional para acompanhamento das requisições de manutenção enviadas pelo Centro de Tecnologia da UFPB à SINFRA.

## Stack

- Django
- HTMX
- Chart.js
- MySQL 8 em container
- Importação de histórico via XLSM/XLSX/CSV

## Funcionalidades do V1

- Backoffice autenticado para equipe interna
- Painel público nativo com filtros e indicadores
- Cadastro e edição de requisições
- Histórico de mudanças de status
- Regras de prioridade e cálculo GUT no backend
- Importador administrativo com suporte ao modelo atual da planilha
- APIs públicas e internas

## Como rodar localmente

1. Copie `.env.example` para `.env`.
2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Rode as migrações:

```bash
python manage.py migrate
```

4. Crie um usuário administrativo:

```bash
python manage.py createsuperuser
```

5. Inicie o servidor:

```bash
python manage.py runserver
```

## Docker

```bash
docker compose up --build
```

O `docker-compose.yml` executa `migrate`, `collectstatic` e inicia o Gunicorn. Para producao, revise as variaveis em `.env.example`, use `DEBUG=False`, uma `SECRET_KEY` forte e configure HTTPS no proxy reverso.

Veja tambem: `docs/PRODUCAO.md`.

## Importação do legado

Via tela interna:

- Faça login com um usuário administrador
- Use a seção de importação no backoffice

Via linha de comando:

```bash
python manage.py importar_requisicoes "CAMINHO_DO_ARQUIVO.xlsm"
```

## Endpoints principais

- `/` painel público
- `/auth/login/` autenticação
- `/painel/` backoffice
- `/api/public/indicadores/`
- `/api/public/requisicoes/`
- `/api/public/requisicoes/{id}/`
- `/api/internal/requisicoes/`
- `/api/internal/importacoes/`
- `/api/internal/regras-prioridade/`
- `/api/internal/cadastros/`

## Testes

```bash
python manage.py test apps.tracker apps.processos --settings=ct_sinfra.settings_test
```
