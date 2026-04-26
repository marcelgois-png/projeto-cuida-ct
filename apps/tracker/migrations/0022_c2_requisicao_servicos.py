from django.db import migrations, models
import django.db.models.deletion


def backfill_requisicao_fks_taxonomia(apps, schema_editor):
    Requisicao = apps.get_model('tracker', 'Requisicao')
    DivisaoSINFRA = apps.get_model('core', 'DivisaoSINFRA')
    TipoServico = apps.get_model('core', 'TipoServico')
    Servico = apps.get_model('core', 'Servico')

    for req in Requisicao.objects.select_related('taxonomia').all():
        divisao_obj = tipo_obj = servico_obj = None

        # Fonte primária: FK taxonomia
        if req.taxonomia:
            taxa = req.taxonomia
            try:
                divisao_obj = DivisaoSINFRA.objects.get(nome=taxa.divisao)
                tipo_obj = TipoServico.objects.get(nome=taxa.tipo_servico, divisao=divisao_obj)
                if taxa.servico:
                    try:
                        servico_obj = Servico.objects.get(nome=taxa.servico, tipo_servico=tipo_obj)
                    except Servico.DoesNotExist:
                        pass
            except (DivisaoSINFRA.DoesNotExist, TipoServico.DoesNotExist):
                print(f'AVISO C2: serviço não encontrado para req {req.numero}: '
                      f'div={taxa.divisao!r} tipo={taxa.tipo_servico!r}')

        # Fallback: CharFields quando taxonomia é nula
        elif req.divisao or req.tipo_servico:
            try:
                divisao_obj = DivisaoSINFRA.objects.get(nome=req.divisao.strip() if req.divisao else '')
                tipo_obj = TipoServico.objects.get(
                    nome=req.tipo_servico.strip() if req.tipo_servico else '',
                    divisao=divisao_obj,
                )
                if req.servico:
                    try:
                        servico_obj = Servico.objects.get(
                            nome=req.servico.strip(),
                            tipo_servico=tipo_obj,
                        )
                    except Servico.DoesNotExist:
                        pass
            except (DivisaoSINFRA.DoesNotExist, TipoServico.DoesNotExist):
                pass

        if divisao_obj or tipo_obj or servico_obj:
            req.divisao_fk = divisao_obj
            req.tipo_servico_fk = tipo_obj
            req.servico_fk = servico_obj
            req.save(update_fields=['divisao_fk', 'tipo_servico_fk', 'servico_fk'])


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    C2 parte 2: em Requisicao, adiciona FKs para DivisaoSINFRA/TipoServico/Servico
    (nomes temporários _fk), faz backfill via taxonomia, remove CharFields antigos
    e FK taxonomia, renomeia FKs para nomes finais.
    """

    dependencies = [
        ('tracker', '0021_move_models_to_core'),
        ('core', '0003_c2_servicos'),
    ]

    operations = [

        # ── Adicionar FKs com nomes temporários ───────────────────────────
        migrations.AddField(
            model_name='requisicao',
            name='divisao_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='requisicoes',
                to='core.divisaosinfra',
                verbose_name='Divisão',
            ),
        ),
        migrations.AddField(
            model_name='requisicao',
            name='tipo_servico_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='requisicoes',
                to='core.tiposervico',
                verbose_name='Tipo de serviço',
            ),
        ),
        migrations.AddField(
            model_name='requisicao',
            name='servico_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='requisicoes',
                to='core.servico',
                verbose_name='Serviço',
            ),
        ),

        # ── Backfill ──────────────────────────────────────────────────────
        migrations.RunPython(backfill_requisicao_fks_taxonomia, reverse_backfill),

        # ── Remover CharFields antigos e FK taxonomia ─────────────────────
        migrations.RemoveField(model_name='requisicao', name='divisao'),
        migrations.RemoveField(model_name='requisicao', name='tipo_servico'),
        migrations.RemoveField(model_name='requisicao', name='servico'),
        migrations.RemoveField(model_name='requisicao', name='taxonomia'),

        # ── Renomear para nomes finais ────────────────────────────────────
        migrations.RenameField(model_name='requisicao', old_name='divisao_fk', new_name='divisao'),
        migrations.RenameField(model_name='requisicao', old_name='tipo_servico_fk', new_name='tipo_servico'),
        migrations.RenameField(model_name='requisicao', old_name='servico_fk', new_name='servico'),
    ]
