from importlib import import_module

from django.db import migrations


def updated_content(content):
    for before, after in (
        ('баками, котлами, химическими миксерами, цехами и баками сырой продукции', 'баками, котлами, цехами, баками сырой продукции и химическими миксерами'),
        ('котлов первичного прогрева, химических миксеров, цехов переработки и баков сырой солярки и сырой веретенки', 'котлов первичного прогрева, цехов переработки, баков сырой солярки и сырой веретенки, химических и финишных миксеров, фильтров и готовых баков'),
        ('Приёмный бак → котёл первичного прогрева → химический миксер → цех переработки → бак сырой солярки или бак сырой веретенки.', 'Приёмный бак → котёл первичного прогрева → цех переработки → бак сырой солярки или бак сырой веретенки → химический миксер → финишный миксер → финишный фильтр → бак готовой продукции.'),
    ):
        content = content.replace(before, after)
    return content


def refresh_route_guides(apps, schema_editor):
    alias = schema_editor.connection.alias
    module = apps.get_model('api', 'Module').objects.using(alias)
    for code, before, after in (
        ('chemical-mixer-loading', 'Движение прогретого масла из котла первичного прогрева в химический миксер.', 'Движение сырой солярки или веретенки из баков в химический миксер.'),
        ('workshop-loading', 'Движение масла из химического миксера в цех переработки.', 'Движение прогретого масла из котла первичного прогрева в цех переработки.'),
    ):
        module.filter(code=code, description=before).update(description=after)
    seed = import_module('api.migrations.0031_seed_knowledge_base')
    previous = import_module('api.migrations.0048_remove_separator')
    articles = apps.get_model('api', 'KnowledgeArticle').objects.using(alias)
    for category, title, summary, content in seed.ARTICLES:
        title, summary, content = previous.updated_guide(title, summary, content)
        updated = updated_content(content)
        if updated != content:
            articles.filter(category__name=category, title=title, summary=summary, content=content).update(content=updated)


class Migration(migrations.Migration):
    dependencies = [('api', '0050_chemical_mixer_after_raw_products')]
    operations = [migrations.RunPython(refresh_route_guides, migrations.RunPython.noop)]
