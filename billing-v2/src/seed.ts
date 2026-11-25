export interface SeedCustomer {
  name: string;
  state: string;
}

export type ProductCategory =
  | "grocery"
  | "dairy"
  | "stationery"
  | "home"
  | "personal_care"
  | "electronics"
  | "apparel";

/** GST slab for each product category. */
export const GST_BY_CATEGORY: Record<ProductCategory, number> = {
  grocery: 5,
  dairy: 12,
  stationery: 12,
  home: 12,
  personal_care: 18,
  electronics: 18,
  apparel: 18,
};

export interface SeedProduct {
  sku: string;
  name: string;
  unitPrice: number;
  category: ProductCategory;
}

export const CUSTOMERS: SeedCustomer[] = [
  { name: "Asha Patil", state: "Maharashtra" },
  { name: "Rohan Deshmukh", state: "Maharashtra" },
  { name: "Kavya Rao", state: "Karnataka" },
  { name: "Nikhil Gowda", state: "Karnataka" },
  { name: "Anjali Nair", state: "Kerala" },
  { name: "Joseph Thomas", state: "Kerala" },
  { name: "Priya Sharma", state: "Delhi" },
  { name: "Vikram Malhotra", state: "Delhi" },
  { name: "Meena Iyer", state: "Tamil Nadu" },
  { name: "Arjun Raman", state: "Tamil Nadu" },
];

export const PRODUCTS: SeedProduct[] = [
  { sku: "SKU-TEA", name: "Assam tea 500g", unitPrice: 240, category: "grocery" },
  { sku: "SKU-RICE", name: "Basmati rice 5kg", unitPrice: 650, category: "grocery" },
  { sku: "SKU-OIL", name: "Groundnut oil 1L", unitPrice: 180, category: "grocery" },
  { sku: "SKU-SOAP", name: "Sandal soap", unitPrice: 45, category: "personal_care" },
  { sku: "SKU-PEN", name: "Gel pen pack", unitPrice: 120, category: "stationery" },
  { sku: "SKU-BOOK", name: "Notebook A4", unitPrice: 85, category: "stationery" },
  { sku: "SKU-BAG", name: "Laptop bag", unitPrice: 1499, category: "electronics" },
  { sku: "SKU-MOUSE", name: "Wireless mouse", unitPrice: 799, category: "electronics" },
  { sku: "SKU-CABLE", name: "USB-C cable", unitPrice: 99.99, category: "electronics" },
  { sku: "SKU-LAMP", name: "Desk lamp", unitPrice: 1250, category: "home" },
  { sku: "SKU-GHEE", name: "Desi ghee 1L", unitPrice: 620, category: "dairy" },
  { sku: "SKU-SHOE", name: "Running shoes", unitPrice: 2999, category: "apparel" },
  { sku: "SKU-TOWEL", name: "Bath towel", unitPrice: 349.5, category: "home" },
  { sku: "SKU-CHARGER", name: "Phone charger", unitPrice: 149.99, category: "electronics" },
  { sku: "SKU-SPICE", name: "Garam masala", unitPrice: 19.99, category: "grocery" },
];
