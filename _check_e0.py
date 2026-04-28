import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ct_sinfra.settings')
django.setup()
from django.db import connection
with connection.cursor() as cur:
    cur.execute("SHOW COLUMNS FROM tracker_requisicao")
    cols = {r[0]: r[1] for r in cur.fetchall()}
    print('empresa type:', cols.get('empresa'))
    print('requisitante_id:', cols.get('requisitante_id'))
    print('nota_empenho_id:', cols.get('nota_empenho_id'))
    cur.execute("SELECT COUNT(*) FROM tracker_requisicao WHERE empresa != ''")
    print('rows with empresa:', cur.fetchone()[0])
    cur.execute("SELECT DISTINCT empresa FROM tracker_requisicao WHERE empresa != '' LIMIT 10")
    print('empresa samples:', [r[0] for r in cur.fetchall()])
    cur.execute("SELECT COUNT(*) FROM core_empresa")
    print('Empresas cadastradas:', cur.fetchone()[0])
