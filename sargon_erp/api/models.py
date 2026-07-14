from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


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
