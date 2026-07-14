from django.urls import path

from .views import login_view
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


urlpatterns = [
    path('auth/login/', login_view, name='auth-login'),
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
]
