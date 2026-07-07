export const emptyUserForm = { id: null, username: '', password: '', first_name: '', last_name: '', email: '', group_id: '', is_active: true }
export const emptyGroupForm = { id: null, name: '', description: '', module_ids: [] }
export const emptyModuleForm = { id: null, code: '', name: '', description: '', is_active: true }
export const emptyPermissionForm = { id: null, code: '', name: '', description: '' }
export const emptySupplierForm = { id: null, company_name: '', city_id: '', address: '', phone: '' }
export const emptyCityForm = { id: null, name: '' }
export const emptyReceiptForm = { id: null, supplier_id: '', input_quantity: '', input_unit: 'liters', can_set_quantity: false, can_complete: false, is_locked: false, is_existing: false }
export const emptyLaboratoryAnalysisForm = {
  id: null,
  density: '',
  flash_point_temperature: '',
  current_temperature: '',
  water_percentage: '',
  is_approved: false,
  is_rejected: false,
}
