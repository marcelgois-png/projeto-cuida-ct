from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from datetime import date


def backfill_encaminhamento_status(apps, schema_editor):
    EncaminhamentoDiretor = apps.get_model('tracker', 'EncaminhamentoDiretor')
    EncaminhamentoDiretor.objects.filter(status='').update(status='PENDENTE')


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    D2: cria VisitaProgramada e expande EncaminhamentoDiretor.

    VisitaProgramada: substitui o armazenamento em localStorage por modelo DB.
    EncaminhamentoDiretor: adiciona status de acompanhamento (PENDENTE /
    EM_ATENDIMENTO / CONCLUIDO), responsavel_assessoria, data_conclusao e
    observacao_atendimento para suportar a tela Mesa da Assessoria.
    """

    dependencies = [
        ('tracker', '0024_c4_empenho_fk'),
        ('core', '0006_d1_lookup_models'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── VisitaProgramada ──────────────────────────────────────────────
        migrations.CreateModel(
            name='VisitaProgramada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('numero', models.PositiveIntegerField(unique=True, editable=False)),
                ('data_visita', models.DateField(verbose_name='Data da visita')),
                ('status', models.CharField(
                    max_length=20,
                    choices=[
                        ('PLANEJADA', 'Planejada'),
                        ('REALIZADA', 'Realizada'),
                        ('CANCELADA', 'Cancelada'),
                    ],
                    default='PLANEJADA',
                    verbose_name='Status',
                )),
                ('observacao', models.TextField(blank=True, verbose_name='Observação')),
                ('criado_por', models.ForeignKey(
                    settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True,
                    blank=True,
                    related_name='visitas_criadas',
                    verbose_name='Criado por',
                )),
            ],
            options={
                'verbose_name': 'Visita Programada',
                'verbose_name_plural': 'Visitas Programadas',
                'ordering': ('-data_visita', '-numero'),
            },
        ),

        migrations.AddField(
            model_name='visitaprogramada',
            name='requisicoes',
            field=models.ManyToManyField(
                to='tracker.Requisicao',
                related_name='visitas_programadas',
                blank=True,
                verbose_name='Requisições',
            ),
        ),

        # ── EncaminhamentoDiretor: expansão ──────────────────────────────
        migrations.AddField(
            model_name='encaminhamentodiretor',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('PENDENTE', 'Pendente'),
                    ('EM_ATENDIMENTO', 'Em atendimento'),
                    ('CONCLUIDO', 'Concluído'),
                ],
                default='PENDENTE',
                verbose_name='Status',
            ),
        ),

        migrations.AddField(
            model_name='encaminhamentodiretor',
            name='responsavel_assessoria',
            field=models.ForeignKey(
                settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='encaminhamentos_assessoria',
                verbose_name='Responsável (assessoria)',
            ),
        ),

        migrations.AddField(
            model_name='encaminhamentodiretor',
            name='data_conclusao',
            field=models.DateField(null=True, blank=True, verbose_name='Data de conclusão'),
        ),

        migrations.AddField(
            model_name='encaminhamentodiretor',
            name='observacao_atendimento',
            field=models.TextField(blank=True, verbose_name='Observação de atendimento'),
        ),

        # Backfill: todos os existentes ficam como PENDENTE
        migrations.RunPython(backfill_encaminhamento_status, reverse_backfill),
    ]
