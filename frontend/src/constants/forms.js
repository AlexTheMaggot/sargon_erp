export const emptyUserForm = { id: null, username: '', password: '', first_name: '', last_name: '', email: '', group_id: '', is_active: true }
export const emptyGroupForm = { id: null, name: '', description: '', module_ids: [], module_permissions: {}, start_module_id: '' }
export const emptyModuleForm = { id: null, code: '', name: '', description: '', default_path: '', is_active: true }
export const emptyPermissionForm = { id: null, code: '', name: '', description: '' }
export const emptySupplierForm = { id: null, company_name: '', city_id: '', address: '', phone: '' }
export const emptyCityForm = { id: null, name: '' }
export const emptyOilFinishingForm = { source_id: '', destination_id: '', volume_liters: '' }
export const emptySorbentCycleForm = { movement_type: 'tank_to_system', source_movement_id: '', system_id: '', quantity: '', note: '' }
export const emptyOilGradeForm = { id: null, name: '', is_active: true }
export const emptyOilManufacturingForms = {
  'concentrate-loading': { equipment_id: '', source_tank_id: '', base_liters: '', warehouse_id: '', item_id: '', polypropylene_quantity: '' },
  'oil-blending': { equipment_id: '', source_tank_id: '', base_liters: '', oil_grade_id: '', concentrate_batch_id: '', concentrate_liters: '' },
  'oil-tank-loading': { batch_id: '', tank_id: '', volume_liters: '' },
  'oil-filling': { tank_id: '', volume_liters: '' },
}
export const emptyInventoryItemForm = { id: null, name: '', category_id: '', unit_id: '', is_active: true, production_material: '', production_product: '', permanent_warehouse_ids: [] }
export const emptyProductionOutputForm = { note: '', lines: [{ item_id: '', disposition: 'good', quantity: '' }], material_usages: [{ source_movement_id: '', quantity: '' }] }
export const emptyProductionLoadingForm = { source_warehouse_id: '', purpose: '', lines: [{ item_id: '', quantity: '' }] }
export const emptyKnowledgeArticleForm = { id: null, title: '', category_id: '', summary: '', content: '' }
export const emptyKnowledgeCategoryForm = { id: null, name: '', description: '' }
export const emptyReceiptForm = { id: null, supplier_id: '', input_quantity: '', input_unit: 'liters', can_set_quantity: false, can_complete: false, is_completed: false, is_locked: false, is_existing: false, batches: [] }
export const emptyLaboratoryAnalysisForm = {
  id: null,
  density: '',
  flash_point_temperature: '',
  current_temperature: '',
  water_percentage: '',
  is_approved: false,
  is_rejected: false,
}
