from importlib import import_module

from django.db import migrations, models


def updated_guide(title, summary, content):
    if title == 'Отгрузка сепаратора и журнал операций':
        return (
            'Журнал производственных операций',
            'История производственных движений и исправление ошибок учёта.',
            '## История' + content.split('## История', 1)[1],
        )
    for before, after in (('сепараторами, ', ''), (', сепараторов', ''), (' → сепаратор', '')):
        content = content.replace(before, after)
    return title, summary, content


def remove_separator_data(apps, schema_editor):
    alias = schema_editor.connection.alias

    def rows(name):
        return apps.get_model('api', name).objects.using(alias)

    container_ids = set(rows('ProductionContainer').filter(kind='separator').values_list('pk', flat=True))
    movement_ids = set(rows('MaterialMovement').filter(
        models.Q(movement_type__in=('boiler_to_separator', 'separator_to_chemical_mixer', 'separator_output'))
        | models.Q(source_container_id__in=container_ids) | models.Q(destination_container_id__in=container_ids),
    ).values_list('pk', flat=True))
    movement_ids.update(rows('MaterialMovement').filter(compensates_id__in=movement_ids).values_list('pk', flat=True))
    rows('MaterialMovement').filter(pk__in=movement_ids, compensates__isnull=False).delete()
    rows('MaterialMovement').filter(pk__in=movement_ids).delete()
    rows('ProductionContainer').filter(pk__in=container_ids).delete()

    module_ids = list(rows('Module').filter(code__in=('separator-loading', 'separator-output')).values_list('pk', flat=True))
    rows('Module').filter(pk__in=module_ids).delete()
    rows('Module').filter(
        code='chemical-mixer-loading', description='Движение очищенного масла из сепаратора в химический миксер.',
    ).update(description='Движение прогретого масла из котла первичного прогрева в химический миксер.')
    audit_filter = models.Q(changes__reason__in=('insufficient_separator_volume', 'separator_overflow')) | models.Q(changes__kind='separator')
    for object_type, identifiers in (
        ('material_movement', movement_ids), ('production_container', container_ids), ('module', module_ids),
    ):
        audit_filter |= models.Q(object_type=object_type, object_id__in=[str(value) for value in identifiers])
    rows('OperationAuditLog').filter(audit_filter).delete()

    seed = import_module('api.migrations.0031_seed_knowledge_base')
    for category, title, summary, content in seed.ARTICLES:
        next_title, next_summary, next_content = updated_guide(title, summary, content)
        if (next_title, next_summary, next_content) != (title, summary, content):
            rows('KnowledgeArticle').filter(category__name=category, title=title, summary=summary, content=content).update(
                title=next_title, summary=next_summary, content=next_content,
            )


class Migration(migrations.Migration):
    dependencies = [('api', '0047_remove_sorbent_schema')]
    operations = [migrations.RunPython(remove_separator_data, migrations.RunPython.noop)]
