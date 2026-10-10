from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Permission(models.Model):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Module(models.Model):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    default_path = models.CharField(max_length=160, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AccessGroup(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    modules = models.ManyToManyField(Module, through='GroupModuleAccess', related_name='access_groups', blank=True)
    start_module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True, related_name='start_groups')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class GroupModuleAccess(models.Model):
    group = models.ForeignKey(AccessGroup, on_delete=models.CASCADE, related_name='module_access')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='group_access')
    permissions = models.ManyToManyField(Permission, related_name='group_module_access', blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['group', 'module'], name='unique_group_module_access'),
        ]
        ordering = ['group__name', 'module__name']

    def __str__(self):
        return f'{self.group} · {self.module}'


class UserProfile(models.Model):
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE, related_name='access_profile')
    group = models.ForeignKey(AccessGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return self.user.get_username()


@receiver(post_save, sender=get_user_model())
def ensure_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


class City(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'cities'

    def __str__(self):
        return self.name


class Supplier(models.Model):
    company_name = models.CharField(max_length=180)
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name='suppliers')
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=120)

    class Meta:
        ordering = ['company_name']

    def __str__(self):
        return self.company_name


class RawMaterialReceipt(models.Model):
    UNIT_LITERS = 'liters'
    UNIT_KILOGRAMS = 'kilograms'
    UNIT_CHOICES = [
        (UNIT_LITERS, 'Литры'),
        (UNIT_KILOGRAMS, 'Килограммы'),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='raw_material_receipts')
    input_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    input_unit = models.CharField(max_length=12, choices=UNIT_CHOICES, default=UNIT_LITERS)
    quantity_liters = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.supplier} · {self.quantity_liters or self.input_quantity}'


class ReceiptBatch(models.Model):
    receipt = models.ForeignKey(RawMaterialReceipt, on_delete=models.CASCADE, related_name='batches')
    sequence_number = models.PositiveIntegerField(default=1)
    input_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    input_unit = models.CharField(max_length=12, choices=RawMaterialReceipt.UNIT_CHOICES, default=RawMaterialReceipt.UNIT_LITERS)
    quantity_liters = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['receipt', 'sequence_number'], name='unique_receipt_batch_number'),
        ]
        ordering = ['receipt_id', 'sequence_number']

    def __str__(self):
        return f'{self.receipt} · Партия #{self.sequence_number}'


class LaboratoryAnalysis(models.Model):
    receipt = models.OneToOneField(RawMaterialReceipt, on_delete=models.CASCADE, related_name='laboratory_analysis', null=True, blank=True)
    batch = models.OneToOneField(ReceiptBatch, on_delete=models.CASCADE, related_name='laboratory_analysis', null=True, blank=True)
    density = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    flash_point_temperature = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    current_temperature = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    water_percentage = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    @property
    def is_filled(self):
        return all([
            self.density is not None,
            self.flash_point_temperature is not None,
            self.current_temperature is not None,
            self.water_percentage is not None,
        ])

    def __str__(self):
        return f'Анализ #{self.pk} · {self.receipt}'


class ProductionContainer(models.Model):
    KIND_RECEIVING_TANK = 'receiving_tank'
    KIND_PREHEATING_BOILER = 'preheating_boiler'
    KIND_SEPARATOR = 'separator'
    KIND_CHEMICAL_MIXER = 'chemical_mixer'
    KIND_PROCESSING_WORKSHOP = 'processing_workshop'
    KIND_RAW_DIESEL_TANK = 'raw_diesel_tank'
    KIND_RAW_SPINDLE_TANK = 'raw_spindle_tank'
    KIND_CHOICES = [
        (KIND_RECEIVING_TANK, 'Приёмный бак'),
        (KIND_PREHEATING_BOILER, 'Котёл первичного прогрева'),
        (KIND_SEPARATOR, 'Сепаратор'),
        (KIND_CHEMICAL_MIXER, 'Химический миксер'),
        (KIND_PROCESSING_WORKSHOP, 'Цех переработки'),
        (KIND_RAW_DIESEL_TANK, 'Бак сырой солярки'),
        (KIND_RAW_SPINDLE_TANK, 'Бак сырой веретенки'),
    ]

    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    number = models.PositiveIntegerField()
    system_code = models.SlugField(max_length=80, unique=True)
    capacity_liters = models.DecimalField(max_digits=14, decimal_places=3)
    current_volume_liters = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['kind', 'number'], name='unique_production_container_number'),
            models.CheckConstraint(condition=models.Q(number__gt=0), name='production_container_number_positive'),
            models.CheckConstraint(condition=models.Q(capacity_liters__gt=0), name='production_container_capacity_positive'),
            models.CheckConstraint(condition=models.Q(current_volume_liters__gte=0), name='production_container_volume_nonnegative'),
            models.CheckConstraint(
                condition=models.Q(current_volume_liters__lte=models.F('capacity_liters')),
                name='production_container_volume_within_capacity',
            ),
        ]
        ordering = ['kind', 'number']

    @property
    def display_name(self):
        prefix = dict(self.KIND_CHOICES)[self.kind]
        return f'{prefix} №{self.number}'

    def __str__(self):
        return self.display_name


class MaterialMovement(models.Model):
    TYPE_RECEIPT_TO_TANK = 'receipt_to_tank'
    TYPE_TANK_TO_BOILER = 'tank_to_boiler'
    TYPE_BOILER_TO_SEPARATOR = 'boiler_to_separator'
    TYPE_SEPARATOR_OUTPUT = 'separator_output'
    TYPE_SEPARATOR_TO_CHEMICAL_MIXER = 'separator_to_chemical_mixer'
    TYPE_CHEMICAL_MIXER_TO_WORKSHOP = 'chemical_mixer_to_workshop'
    TYPE_WORKSHOP_TO_RAW_DIESEL_TANK = 'workshop_to_raw_diesel_tank'
    TYPE_WORKSHOP_TO_RAW_SPINDLE_TANK = 'workshop_to_raw_spindle_tank'
    TYPE_COMPENSATION = 'compensation'
    TYPE_CHOICES = [
        (TYPE_RECEIPT_TO_TANK, 'Поступление из приёмки'),
        (TYPE_TANK_TO_BOILER, 'Загрузка котла'),
        (TYPE_BOILER_TO_SEPARATOR, 'Загрузка сепаратора'),
        (TYPE_SEPARATOR_OUTPUT, 'Отгрузка сепаратора'),
        (TYPE_SEPARATOR_TO_CHEMICAL_MIXER, 'Загрузка химического миксера'),
        (TYPE_CHEMICAL_MIXER_TO_WORKSHOP, 'Загрузка в цех переработки'),
        (TYPE_WORKSHOP_TO_RAW_DIESEL_TANK, 'Загрузка бака сырой солярки'),
        (TYPE_WORKSHOP_TO_RAW_SPINDLE_TANK, 'Загрузка бака сырой веретенки'),
        (TYPE_COMPENSATION, 'Компенсирующее движение'),
    ]

    PRODUCT_TECHNICAL_WATER = 'Техническая вода'
    PRODUCT_TECHNICAL_WASTE = 'Технический мусор'

    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, 'Подтверждено'),
    ]

    movement_number = models.CharField(max_length=40, unique=True)
    movement_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    source_container = models.ForeignKey(
        ProductionContainer,
        on_delete=models.PROTECT,
        related_name='outgoing_movements',
        null=True,
        blank=True,
    )
    destination_container = models.ForeignKey(
        ProductionContainer,
        on_delete=models.PROTECT,
        related_name='incoming_movements',
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=120, default='Отработанное масло')
    volume_liters = models.DecimalField(max_digits=14, decimal_places=3)
    moved_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='material_movements',
        null=True,
        blank=True,
    )
    receipt = models.ForeignKey(
        RawMaterialReceipt,
        on_delete=models.SET_NULL,
        related_name='material_movements',
        null=True,
        blank=True,
    )
    receipt_batch = models.ForeignKey(
        ReceiptBatch,
        on_delete=models.SET_NULL,
        related_name='material_movements',
        null=True,
        blank=True,
    )
    compensates = models.OneToOneField(
        'self',
        on_delete=models.PROTECT,
        related_name='compensation',
        null=True,
        blank=True,
    )
    is_compensated = models.BooleanField(default=False)
    source_event_key = models.CharField(max_length=160, unique=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True)
    source_snapshot = models.CharField(max_length=180, blank=True)
    destination_snapshot = models.CharField(max_length=180, blank=True)
    receipt_snapshot = models.CharField(max_length=180, blank=True)
    batch_snapshot = models.CharField(max_length=180, blank=True)
    source_volume_before = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    source_volume_after = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    destination_volume_before = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    destination_volume_after = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    reason = models.TextField(blank=True)
    system_description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(volume_liters__gt=0), name='material_movement_volume_positive'),
        ]
        ordering = ['-moved_at', '-id']

    def __str__(self):
        return self.movement_number


class OperationAuditLog(models.Model):
    RESULT_SUCCESS = 'success'
    RESULT_REJECTED = 'rejected'
    RESULT_CHOICES = [
        (RESULT_SUCCESS, 'Успешно'),
        (RESULT_REJECTED, 'Отклонено'),
    ]

    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80, blank=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default=RESULT_SUCCESS)
    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='operation_audit_logs',
        null=True,
        blank=True,
    )
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.action} · {self.object_type} #{self.object_id}'


class InventoryCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    DECIMAL_PLACES_CHOICES = [(0, 'Целые'), (1, 'Десятые'), (2, 'Сотые')]

    name = models.CharField(max_length=120, unique=True)
    symbol = models.CharField(max_length=20, unique=True)
    decimal_places = models.PositiveSmallIntegerField(choices=DECIMAL_PLACES_CHOICES, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.symbol


class InventoryItem(models.Model):
    name = models.CharField(max_length=180, unique=True)
    category = models.ForeignKey(InventoryCategory, on_delete=models.PROTECT, related_name='items')
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items')
    last_purchase_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(last_purchase_price__gte=0),
                name='inventory_item_purchase_price_nonnegative',
            ),
        ]

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class WarehouseBalance(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='balances')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='warehouse_balances')
    quantity = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    average_unit_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['warehouse__name', 'item__name']
        constraints = [
            models.UniqueConstraint(fields=['warehouse', 'item'], name='unique_warehouse_item_balance'),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name='warehouse_balance_quantity_nonnegative'),
            models.CheckConstraint(
                condition=models.Q(average_unit_cost__gte=0),
                name='warehouse_balance_average_cost_nonnegative',
            ),
        ]

    def __str__(self):
        return f'{self.warehouse} · {self.item}: {self.quantity}'


class WarehouseDocumentSequence(models.Model):
    document_type = models.CharField(max_length=20)
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['document_type', 'year'], name='unique_warehouse_document_sequence'),
        ]


class WarehouseDocument(models.Model):
    TYPE_RECEIPT = 'receipt'
    TYPE_ISSUE = 'issue'
    TYPE_TRANSFER = 'transfer'
    TYPE_INVENTORY = 'inventory'
    TYPE_CHOICES = [
        (TYPE_RECEIPT, 'Поступление'),
        (TYPE_ISSUE, 'Внутренний расход'),
        (TYPE_TRANSFER, 'Перемещение'),
        (TYPE_INVENTORY, 'Инвентаризация'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_POSTED = 'posted'
    STATUS_IN_TRANSIT = 'in_transit'
    STATUS_COMPLETED = 'completed'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Черновик'),
        (STATUS_POSTED, 'Проведён'),
        (STATUS_IN_TRANSIT, 'В пути'),
        (STATUS_COMPLETED, 'Завершён'),
        (STATUS_REJECTED, 'Отклонён'),
        (STATUS_CANCELLED, 'Отменён'),
    ]

    number = models.CharField(max_length=40, unique=True)
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    document_date = models.DateTimeField(default=timezone.now)
    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='outgoing_documents',
        null=True,
        blank=True,
    )
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='incoming_documents',
        null=True,
        blank=True,
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='warehouse_receipts',
        null=True,
        blank=True,
    )
    purpose = models.TextField(blank=True)
    created_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='created_warehouse_documents',
        null=True,
    )
    posted_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='posted_warehouse_documents',
        null=True,
        blank=True,
    )
    confirmed_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='confirmed_warehouse_documents',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-document_date', '-id']

    def __str__(self):
        return self.number


class WarehouseDocumentLine(models.Model):
    document = models.ForeignKey(WarehouseDocument, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='document_lines')
    quantity = models.DecimalField(max_digits=18, decimal_places=2)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['document', 'item'], name='unique_warehouse_document_item'),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name='warehouse_document_line_quantity_nonnegative'),
            models.CheckConstraint(
                condition=models.Q(unit_price__isnull=True) | models.Q(unit_price__gte=0),
                name='warehouse_document_line_unit_price_nonnegative',
            ),
        ]

    def __str__(self):
        return f'{self.document} · {self.item}'


class WarehouseMovement(models.Model):
    TYPE_RECEIPT = 'receipt'
    TYPE_ISSUE = 'issue'
    TYPE_TRANSFER_OUT = 'transfer_out'
    TYPE_TRANSFER_IN = 'transfer_in'
    TYPE_TRANSFER_RETURN = 'transfer_return'
    TYPE_INVENTORY = 'inventory'
    TYPE_REVERSAL = 'reversal'
    TYPE_CHOICES = [
        (TYPE_RECEIPT, 'Поступление'),
        (TYPE_ISSUE, 'Внутренний расход'),
        (TYPE_TRANSFER_OUT, 'Отправка перемещения'),
        (TYPE_TRANSFER_IN, 'Получение перемещения'),
        (TYPE_TRANSFER_RETURN, 'Возврат перемещения'),
        (TYPE_INVENTORY, 'Корректировка инвентаризации'),
        (TYPE_REVERSAL, 'Отмена документа'),
    ]

    document = models.ForeignKey(WarehouseDocument, on_delete=models.PROTECT, related_name='movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='movements')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='warehouse_movements')
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    quantity_delta = models.DecimalField(max_digits=18, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    total_value_delta = models.DecimalField(max_digits=20, decimal_places=2)
    created_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='warehouse_movements',
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(condition=~models.Q(quantity_delta=0), name='warehouse_movement_quantity_nonzero'),
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name='warehouse_movement_unit_cost_nonnegative'),
        ]

    def __str__(self):
        return f'{self.document} · {self.item}'


class KnowledgeCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class KnowledgeArticle(models.Model):
    category = models.ForeignKey(KnowledgeCategory, on_delete=models.PROTECT, related_name='articles')
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=500, blank=True)
    content = models.TextField()
    created_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='created_knowledge_articles',
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='updated_knowledge_articles',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__name', 'title', 'id']

    def __str__(self):
        return self.title
