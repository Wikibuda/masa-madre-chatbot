import os
import json
import shopify
from dotenv import load_dotenv

def setup_shopify_api():
    """Configura la conexión con la API de Shopify"""
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener credenciales
    api_key = os.getenv('SHOPIFY_API_KEY')
    password = os.getenv('SHOPIFY_PASSWORD')
    store_url = os.getenv('SHOPIFY_STORE_URL')
    
    if not all([api_key, password, store_url]):
        raise ValueError("Faltan credenciales de Shopify en el archivo .env")
    
    # Configurar la sesión
    session = shopify.Session(store_url, '2023-10', password)
    shopify.ShopifyResource.activate_session(session)
    
    print("✅ Conexión con Shopify API establecida")
    return shopify

def get_all_products(shopify_module, limit=250):
    """Obtiene todos los productos de la tienda con paginación correcta"""
    print(f"🔄 Obteniendo productos de Shopify (límite: {limit})...")
    
    # Obtener la primera página
    products = shopify_module.Product.find(limit=limit)
    all_products = list(products)
    
    # Manejar paginación CORRECTAMENTE
    while products.has_next_page():
        products = products.next_page()
        all_products.extend(products)
    
    print(f"✅ {len(all_products)} productos obtenidos")
    return all_products

def clean_shopify_product(product):
    """Limpia y normaliza los datos de un producto de Shopify"""
    # Convertir a diccionario
    product_data = {
        'id': product.id,
        'handle': product.handle,
        'title': product.title,
        'body_html': product.body_html,
        'vendor': product.vendor,
        'product_type': product.product_type,
        'created_at': str(product.created_at),
        'updated_at': str(product.updated_at),
        'published_at': str(product.published_at) if product.published_at else None,
        'tags': product.tags.split(',') if product.tags else [],
        'variants': []
    }
    
    # Procesar variantes
    for variant in product.variants:
        variant_data = {
            'id': variant.id,
            'title': variant.title,
            'price': variant.price,
            'sku': variant.sku,
            'position': variant.position,
            'inventory_policy': variant.inventory_policy,
            'compare_at_price': variant.compare_at_price,
            'fulfillment_service': variant.fulfillment_service,
            'inventory_management': variant.inventory_management,
            'inventory_quantity': variant.inventory_quantity,
            'taxable': variant.taxable,
            'weight': variant.weight,
            'weight_unit': variant.weight_unit
        }
        product_data['variants'].append(variant_data)
    
    # Obtener imágenes
    images = shopify.Image.find(product_id=product.id)
    product_data['images'] = [{
        'id': img.id,
        'src': img.src,
        'position': img.position
    } for img in images]
    
    # Obtener metafields (si existen)
    metafields = shopify.Metafield.find(resource='products', resource_id=product.id)
    product_data['metafields'] = [{
        'key': mf.key,
        'value': mf.value,
        'namespace': mf.namespace,
        'description': mf.description
    } for mf in metafields]
    
    return product_data

def get_all_products_cleaned():
    """Obtiene y limpia todos los productos de Shopify"""
    shopify = setup_shopify_api()
    raw_products = get_all_products(shopify)
    
    cleaned_products = []
    for product in raw_products:
        cleaned = clean_shopify_product(product)
        cleaned_products.append(cleaned)
    
    # Cerrar sesión
    shopify.ShopifyResource.clear_session()
    
    return cleaned_products

if __name__ == "__main__":
    # Obtener productos limpios
    products = get_all_products_cleaned()
    
    # Guardar para usar en el procesador semántico
    with open('shopify_products.json', 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    print(f"✅ {len(products)} productos guardados en shopify_products.json")
    
    # Mostrar ejemplo
    print("\nEjemplo de producto guardado (primeros 500 caracteres):")
    print(str(products[0])[:500] + "...")
