from importlib import import_module

from django.db import migrations


OLD_APPROVAL_TEXT = 'Для одобрения заполните все показатели.'
NEW_APPROVAL_TEXT = (
    'Для одобрения заполните плотность и текущую температуру. '
    'Температура вспышки и количество воды необязательны; пустые значения не заменяются нулями.'
)


def update_laboratory_guide(apps, schema_editor):
    Article = apps.get_model('api', 'KnowledgeArticle')
    seed = import_module('api.migrations.0031_seed_knowledge_base')
    for category, title, summary, content in seed.ARTICLES:
        if title == 'Проведение анализа и принятие решения':
            Article.objects.using(schema_editor.connection.alias).filter(
                category__name=category, title=title, summary=summary, content=content,
            ).update(content=content.replace(OLD_APPROVAL_TEXT, NEW_APPROVAL_TEXT))


class Migration(migrations.Migration):
    dependencies = [('api', '0044_seed_production_workspace')]
    operations = [migrations.RunPython(update_laboratory_guide, migrations.RunPython.noop)]
