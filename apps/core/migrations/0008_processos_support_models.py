"""
Migration: adiciona StatusProcesso, SituacaoSIPAC, GerenciaSINFRA, ServicoProcesso
e popula com dados iniciais do documento mestre v1.4.
"""

from django.db import migrations, models
import django.utils.timezone


def popular_dados(apps, schema_editor):
    StatusProcesso = apps.get_model('core', 'StatusProcesso')
    SituacaoSIPAC = apps.get_model('core', 'SituacaoSIPAC')
    GerenciaSINFRA = apps.get_model('core', 'GerenciaSINFRA')

    for codigo, nome, ordem in [
        ('01', 'Encaminhar para análise e orçamento', 1),
        ('02', 'Em análise técnica e orçamento', 2),
        ('03', 'Revisar soluções e orçamento', 3),
        ('04', 'Aguardando disponibilidade de orçamento', 4),
        ('05', 'Execução Autorizada', 5),
        ('06', 'Emissão da ordem de serviço', 6),
        ('07', 'Em execução', 7),
        ('08', 'Serviço Realizado', 8),
        ('09', 'Serviço temporariamente suspenso', 9),
        ('10', 'Serviço em revisão', 10),
        ('11', 'Processo congelado', 11),
        ('12', 'Processo perde objeto', 12),
        ('13', 'SINFRA', 13),
    ]:
        StatusProcesso.objects.create(codigo=codigo, nome=nome, ordem=ordem)

    for nome in ['ATIVO', 'ARQUIVADO', 'APENSADO']:
        SituacaoSIPAC.objects.create(nome=nome)

    for nome in [
        'Gerência de Manutenção e Equipamentos',
        'Gerência de Eletricidade',
        'Gerência de Projetos e Edificações',
        'Gerência de Almoxarifado, Cadastro e Patrimônio Setorial',
        'Telefonia',
        'Superintendência de Infraestrutura',
    ]:
        GerenciaSINFRA.objects.create(nome=nome)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_cleanup_status_requisicao'),
    ]

    operations = [
        migrations.CreateModel(
            name='StatusProcesso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('codigo', models.CharField(max_length=10, unique=True)),
                ('nome', models.CharField(max_length=200)),
                ('ordem', models.IntegerField(default=0)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Status de Processo',
                'verbose_name_plural': 'Status de Processo',
                'db_table': 'core_statusprocesso',
                'ordering': ['ordem'],
            },
        ),
        migrations.CreateModel(
            name='SituacaoSIPAC',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=50, unique=True)),
                ('ativa', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Situação SIPAC',
                'verbose_name_plural': 'Situações SIPAC',
                'db_table': 'core_situacaosipac',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='GerenciaSINFRA',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=200, unique=True)),
                ('ativa', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Gerência SINFRA',
                'verbose_name_plural': 'Gerências SINFRA',
                'db_table': 'core_gerenciasinfra',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='ServicoProcesso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=200, unique=True)),
                ('ordem', models.IntegerField(blank=True, default=0, null=True)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Serviço de Processo',
                'verbose_name_plural': 'Serviços de Processo',
                'db_table': 'core_servicoprocesso',
                'ordering': ['ordem', 'nome'],
            },
        ),
        migrations.RunPython(popular_dados, noop),
    ]
