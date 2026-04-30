"""
Renomeia os campos created/modified para criado_em/atualizado_em nos modelos
adicionados pela migration 0008, alinhando com o TimeStampedModel do projeto.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_processos_support_models'),
    ]

    operations = [
        # StatusProcesso
        migrations.RenameField(
            model_name='statusprocesso',
            old_name='created',
            new_name='criado_em',
        ),
        migrations.RenameField(
            model_name='statusprocesso',
            old_name='modified',
            new_name='atualizado_em',
        ),
        # SituacaoSIPAC
        migrations.RenameField(
            model_name='situacaosipac',
            old_name='created',
            new_name='criado_em',
        ),
        migrations.RenameField(
            model_name='situacaosipac',
            old_name='modified',
            new_name='atualizado_em',
        ),
        # GerenciaSINFRA
        migrations.RenameField(
            model_name='gerenciasinfra',
            old_name='created',
            new_name='criado_em',
        ),
        migrations.RenameField(
            model_name='gerenciasinfra',
            old_name='modified',
            new_name='atualizado_em',
        ),
        # ServicoProcesso
        migrations.RenameField(
            model_name='servicoprocesso',
            old_name='created',
            new_name='criado_em',
        ),
        migrations.RenameField(
            model_name='servicoprocesso',
            old_name='modified',
            new_name='atualizado_em',
        ),
    ]
