export const money = amount => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
export function category(product) {
  const text = `${product.name} ${product.description || ''}`.toLowerCase();
  if (/headphone|speaker|audio|earbud|keyboard|mouse|monitor|camera|charger|laptop|computer/.test(text)) return 'Tech & audio';
  if (/chair|lamp|light|table|sofa|vase|home|ceramic|candle/.test(text)) return 'Living';
  return 'Everyday carry';
}
export function artwork(product) {
  const text = product.name.toLowerCase();
  if (/chair|sofa|seat/.test(text)) return 'chair';
  if (/lamp|light|vase|candle|ceramic/.test(text)) return 'lamp';
  if (/watch|clock/.test(text)) return 'watch';
  if (/bag|tote|backpack|carry/.test(text)) return 'bag';
  if (/speaker|radio/.test(text)) return 'speaker';
  if (/headphone|earbud|audio/.test(text)) return 'headphones';
  return null;
}
export function filterProducts(products, { search = '', selected = 'All objects', sort = 'featured', favorites = null } = {}) {
  let result = products.filter(product =>
    (selected === 'All objects' || category(product) === selected) &&
    `${product.name} ${product.description || ''}`.toLowerCase().includes(search.toLowerCase().trim()) &&
    (!favorites || favorites.includes(product.id)));
  if (sort === 'price-asc') result.sort((a, b) => a.price - b.price);
  if (sort === 'price-desc') result.sort((a, b) => b.price - a.price);
  if (sort === 'name') result.sort((a, b) => a.name.localeCompare(b.name));
  return result;
}
export function sanitizeCart(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  return value.filter(item => {
    if (!item || typeof item.id !== 'string' || !item.id || seen.has(item.id) || typeof item.name !== 'string' || !Number.isFinite(item.price) || item.price <= 0 || !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 99) return false;
    seen.add(item.id);
    return true;
  }).map(({ id, name, price, quantity }) => ({ id, name, price, quantity }));
}
export function cartTotal(cart) {
  return cart.reduce((sum, item) => sum + Math.round(item.price * 100) * item.quantity, 0) / 100;
}
export function addToCart(cart, product) {
  const existing = cart.find(item => item.id === product.id);
  if ((existing?.quantity || 0) >= Math.min(product.stock_quantity, 99)) throw new Error('That’s all the available stock for this item.');
  if (existing) return cart.map(item => item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item);
  return [...cart, { id: product.id, name: product.name, price: product.price, quantity: 1 }];
}
export function reconcileCart(cart, products) {
  let changed = false;
  const items = cart.flatMap(item => {
    const product = products.find(p => p.id === item.id);
    if (!product || product.stock_quantity < 1) { changed = true; return []; }
    const quantity = Math.min(item.quantity, product.stock_quantity, 99);
    if (product.price !== item.price || quantity !== item.quantity) changed = true;
    return [{ id: item.id, name: product.name, price: product.price, quantity }];
  });
  return { items, changed };
}
export const demoProducts = [
  { id: 'demo-headphones', name: 'Studio wireless headphones', description: 'A quieter kind of everyday. Soft ear cushions, a considered silhouette, and room to tune into what matters.', price: 129, stock_quantity: 12 },
  { id: 'demo-lamp', name: 'Milo table lamp', description: 'A sculptural silhouette and a warm, welcoming glow. The perfect companion for your reading corner.', price: 89, stock_quantity: 8 },
  { id: 'demo-bag', name: 'The everyday tote', description: 'A place for everything you carry. A generous canvas tote with an easy silhouette and a thoughtfully placed front pocket.', price: 48, stock_quantity: 20 },
  { id: 'demo-chair', name: 'Sunday lounge chair', description: 'An invitation to slow down. Sculpted oak and soft sage upholstery meet in a chair made for your favorite corner.', price: 249, stock_quantity: 4 },
  { id: 'demo-watch', name: 'Tempo everyday watch', description: 'A considered approach to keeping time. A soft everyday strap and a clean face that goes with whatever comes next.', price: 159, stock_quantity: 9 },
  { id: 'demo-speaker', name: 'Pebble portable speaker', description: 'Your soundtrack, wherever you find yourself. A tactile woven finish and an easy carry loop for life in motion.', price: 79, stock_quantity: 14 },
];
