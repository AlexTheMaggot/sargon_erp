from django.urls import path

from .views import login_view
from .views import login_options_view
from .views import me_view
from .views import access_group_detail_view
from .views import access_groups_view
from .views import access_module_detail_view
from .views import access_modules_view
from .views import access_permission_detail_view
from .views import access_permissions_view
from .views import access_user_detail_view
from .views import access_users_view
from .views import directory_city_detail_view
from .views import directory_cities_view
from .views import directory_supplier_detail_view
from .views import directory_suppliers_view
from .views import laboratory_analyses_view
from .views import laboratory_analysis_detail_view
from .views import raw_material_batch_detail_view
from .views import raw_material_receipt_batches_view
from .views import raw_material_receipt_detail_view
from .views import raw_material_receipts_view
from .views import receiving_tanks_view
from .views import preheating_boilers_view
from .views import production_container_detail_view
from .views import tank_to_boiler_movements_view
from .views import compensate_movement_view
from .views import processing_journal_view
from .views import production_overview_view
from .views import separators_view
from .views import boiler_to_separator_movements_view
from .views import separator_output_movements_view
from .views import chemical_mixers_view
from .views import separator_to_chemical_mixer_movements_view
from .views import processing_workshops_view
from .views import chemical_mixer_to_workshop_movements_view
from .views import raw_diesel_tanks_view
from .views import raw_spindle_tanks_view
from .views import workshop_to_raw_diesel_tank_movements_view
from .views import workshop_to_raw_spindle_tank_movements_view
from .views import inventory_categories_view
from .views import inventory_category_detail_view
from .views import units_of_measure_view
from .views import unit_of_measure_detail_view
from .views import inventory_items_view
from .views import inventory_item_detail_view
from .views import warehouses_view
from .views import warehouse_detail_view
from .views import warehouse_reference_data_view
from .views import warehouse_overview_view
from .views import warehouse_documents_view
from .views import warehouse_document_detail_view
from .views import warehouse_document_post_view
from .views import warehouse_transfer_decision_view
from .views import warehouse_document_cancel_view
from .views import knowledge_categories_view
from .views import knowledge_category_detail_view
from .views import knowledge_articles_view
from .views import knowledge_article_detail_view


urlpatterns = [
    path('knowledge/categories/', knowledge_categories_view, name='knowledge-categories'),
    path('knowledge/categories/<int:category_id>/', knowledge_category_detail_view, name='knowledge-category-detail'),
    path('knowledge/articles/', knowledge_articles_view, name='knowledge-articles'),
    path('knowledge/articles/<int:article_id>/', knowledge_article_detail_view, name='knowledge-article-detail'),
    path('auth/login/', login_view, name='auth-login'),
    path('auth/login-options/', login_options_view, name='auth-login-options'),
    path('auth/me/', me_view, name='auth-me'),
    path('access/users/', access_users_view, name='access-users'),
    path('access/users/<int:user_id>/', access_user_detail_view, name='access-user-detail'),
    path('access/groups/', access_groups_view, name='access-groups'),
    path('access/groups/<int:group_id>/', access_group_detail_view, name='access-group-detail'),
    path('access/modules/', access_modules_view, name='access-modules'),
    path('access/modules/<int:module_id>/', access_module_detail_view, name='access-module-detail'),
    path('access/permissions/', access_permissions_view, name='access-permissions'),
    path('access/permissions/<int:permission_id>/', access_permission_detail_view, name='access-permission-detail'),
    path('directories/cities/', directory_cities_view, name='directory-cities'),
    path('directories/cities/<int:city_id>/', directory_city_detail_view, name='directory-city-detail'),
    path('directories/suppliers/', directory_suppliers_view, name='directory-suppliers'),
    path('directories/suppliers/<int:supplier_id>/', directory_supplier_detail_view, name='directory-supplier-detail'),
    path('raw-material/receipts/', raw_material_receipts_view, name='raw-material-receipts'),
    path('raw-material/receipts/<int:receipt_id>/', raw_material_receipt_detail_view, name='raw-material-receipt-detail'),
    path('raw-material/receipts/<int:receipt_id>/batches/', raw_material_receipt_batches_view, name='raw-material-receipt-batches'),
    path('raw-material/batches/<int:batch_id>/', raw_material_batch_detail_view, name='raw-material-batch-detail'),
    path('laboratory/analyses/', laboratory_analyses_view, name='laboratory-analyses'),
    path('laboratory/analyses/<int:analysis_id>/', laboratory_analysis_detail_view, name='laboratory-analysis-detail'),
    path('processing/receiving-tanks/', receiving_tanks_view, name='processing-receiving-tanks'),
    path('processing/preheating-boilers/', preheating_boilers_view, name='processing-preheating-boilers'),
    path('processing/separators/', separators_view, name='processing-separators'),
    path('processing/chemical-mixers/', chemical_mixers_view, name='processing-chemical-mixers'),
    path('processing/workshops/', processing_workshops_view, name='processing-workshops'),
    path('processing/raw-diesel-tanks/', raw_diesel_tanks_view, name='processing-raw-diesel-tanks'),
    path('processing/raw-spindle-tanks/', raw_spindle_tanks_view, name='processing-raw-spindle-tanks'),
    path('processing/containers/<int:container_id>/', production_container_detail_view, name='processing-container-detail'),
    path('processing/movements/tank-to-boiler/', tank_to_boiler_movements_view, name='processing-tank-to-boiler'),
    path('processing/movements/boiler-to-separator/', boiler_to_separator_movements_view, name='processing-boiler-to-separator'),
    path('processing/movements/separator-output/', separator_output_movements_view, name='processing-separator-output'),
    path('processing/movements/separator-to-chemical-mixer/', separator_to_chemical_mixer_movements_view, name='processing-separator-to-chemical-mixer'),
    path('processing/movements/chemical-mixer-to-workshop/', chemical_mixer_to_workshop_movements_view, name='processing-chemical-mixer-to-workshop'),
    path('processing/movements/workshop-to-raw-diesel-tank/', workshop_to_raw_diesel_tank_movements_view, name='processing-workshop-to-raw-diesel-tank'),
    path('processing/movements/workshop-to-raw-spindle-tank/', workshop_to_raw_spindle_tank_movements_view, name='processing-workshop-to-raw-spindle-tank'),
    path('processing/movements/<int:movement_id>/compensate/', compensate_movement_view, name='processing-movement-compensate'),
    path('processing/journal/', processing_journal_view, name='processing-journal'),
    path('dashboard/overview/', production_overview_view, name='production-overview'),
    path('warehouse/settings/categories/', inventory_categories_view, name='warehouse-categories'),
    path('warehouse/settings/categories/<int:category_id>/', inventory_category_detail_view, name='warehouse-category-detail'),
    path('warehouse/settings/units/', units_of_measure_view, name='warehouse-units'),
    path('warehouse/settings/units/<int:unit_id>/', unit_of_measure_detail_view, name='warehouse-unit-detail'),
    path('warehouse/settings/items/', inventory_items_view, name='warehouse-items'),
    path('warehouse/settings/items/<int:item_id>/', inventory_item_detail_view, name='warehouse-item-detail'),
    path('warehouse/settings/warehouses/', warehouses_view, name='warehouses'),
    path('warehouse/settings/warehouses/<int:warehouse_id>/', warehouse_detail_view, name='warehouse-detail'),
    path('warehouse/reference-data/', warehouse_reference_data_view, name='warehouse-reference-data'),
    path('warehouse/overview/', warehouse_overview_view, name='warehouse-overview'),
    path('warehouse/documents/', warehouse_documents_view, name='warehouse-documents'),
    path('warehouse/documents/<int:document_id>/', warehouse_document_detail_view, name='warehouse-document-detail'),
    path('warehouse/documents/<int:document_id>/post/', warehouse_document_post_view, name='warehouse-document-post'),
    path('warehouse/documents/<int:document_id>/transfer-decision/', warehouse_transfer_decision_view, name='warehouse-transfer-decision'),
    path('warehouse/documents/<int:document_id>/cancel/', warehouse_document_cancel_view, name='warehouse-document-cancel'),
]
