from django.db import migrations, models


METODOS_INICIAIS = [
    ('Contrato', 'Execução por empresa contratada'),
    ('Execução Própria', 'Executado pela equipe interna da SINFRA'),
    ('Visita Técnica', 'Inspeção in loco antes da execução'),
    ('Chamado Externo', 'Demanda encaminhada a órgão externo'),
    ('Manutenção Preventiva', 'Ação programada de manutenção preventiva'),
]

AMBIENTES_INICIAIS = [
    'Sala de Aula',
    'Laboratório',
    'Banheiro',
    'Área Administrativa',
    'Área Externa',
    'Auditório / Teatro',
    'Biblioteca',
    'Bloco de Ensino',
    'Corredor / Circulação',
    'Estacionamento',
    'Refeitório / Cantina',
    'Sala de Reunião',
]


def seed_lookup_data(apps, schema_editor):
    MetodoPriorizacao = apps.get_model('core', 'MetodoPriorizacao')
    TipoAmbiente = apps.get_model('core', 'TipoAmbiente')
    for nome, descricao in METODOS_INICIAIS:
        MetodoPriorizacao.objects.get_or_create(nome=nome, defaults={'descricao': descricao})
    for nome in AMBIENTES_INICIAIS:
        TipoAmbiente.objects.get_or_create(nome=nome)


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """D1: cria MetodoPriorizacao e TipoAmbiente com dados iniciais."""

    dependencies = [
        ('core', '0005_c4_empenho'),
    ]

    operations = [

        migrations.CreateModel(
            name='MetodoPriorizacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=100, unique=True)),
                ('descricao', models.TextField(blank=True)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Método de priorização',
                'verbose_name_plural': 'Métodos de priorização',
                'ordering': ('nome',),
                'db_table': 'core_metodopriorizacao',
            },
        ),

        migrations.CreateModel(
            name='TipoAmbiente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=100, unique=True)),
                ('descricao', models.TextField(blank=True)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Tipo de ambiente',
                'verbose_name_plural': 'Tipos de ambiente',
                'ordering': ('nome',),
                'db_table': 'core_tipoambiente',
            },
        ),

        migrations.RunPython(seed_lookup_data, reverse_seed),
    ]
