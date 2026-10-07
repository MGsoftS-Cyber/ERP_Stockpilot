// Teaching edition: Describe JSON shapes; static types do not validate runtime responses.
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
}

export type Role =
  | "ADMINISTRATOR"
  | "MANAGER"
  | "STOCK_OPERATOR"
  | "PURCHASING_AGENT"
  | "SALES_AGENT"
  | "ACCOUNTANT"
  | "VIEWER";

export interface Membership {
  id: string;
  organization: Organization;
  role: Role;
  role_label: string;
  is_active: boolean;
}

export interface CurrentUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  memberships: Membership[];
}

export interface Category {
  id: string;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
}

export interface UnitOfMeasure {
  id: string;
  name: string;
  symbol: string;
  allows_decimals: boolean;
}

export interface TaxRate {
  id: string;
  name: string;
  rate: string;
  is_active: boolean;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  description: string;
  category: string | null;
  category_name: string;
  unit: string;
  unit_symbol: string;
  tax_rate: string | null;
  tax_rate_value: string | null;
  purchase_price: string;
  selling_price: string;
  minimum_stock: string;
  is_active: boolean;
}

export interface BusinessPartner {
  id: string;
  code: string;
  name: string;
  partner_type: "CUSTOMER" | "SUPPLIER" | "BOTH";
  partner_type_label: string;
  email: string;
  phone: string;
  address: string;
  is_active: boolean;
}

export interface Warehouse {
  id: string;
  code: string;
  name: string;
  address: string;
  is_active: boolean;
}

export interface StockBalance {
  id: string;
  product: string;
  product_sku: string;
  product_name: string;
  warehouse: string;
  warehouse_code: string;
  warehouse_name: string;
  on_hand: string;
  reserved: string;
  available: string;
  is_low_stock: boolean;
  updated_at: string;
}

export interface StockMovement {
  id: string;
  product: string;
  product_sku: string;
  product_name: string;
  warehouse: string;
  warehouse_code: string;
  movement_type: string;
  movement_type_label: string;
  quantity_signed: string;
  unit_cost: string;
  occurred_at: string;
  source_type: string;
  source_id: string;
  idempotency_key: string;
  created_by_email: string | null;
  created_at: string;
}

export interface StockReservation {
  id: string;
  product: string;
  product_sku: string;
  warehouse: string;
  warehouse_code: string;
  quantity: string;
  source_type: "MANUAL" | "SALES_ORDER" | "OTHER";
  source_id: string;
  status: "ACTIVE" | "RELEASED" | "FULFILLED";
  fulfilled_quantity: string;
  status_label: string;
  idempotency_key: string;
  created_at: string;
  released_at: string | null;
}
