class Product {
  const Product({
    required this.productId,
    required this.name,
    this.description,
    this.category,
    this.brand,
    this.price,
    this.imageUrl,
    this.rating,
    this.tags = const [],
    this.isActive = true,
    this.inStock = true,
  });

  final String productId;
  final String name;
  final String? description;
  final String? category;
  final String? brand;
  final double? price;
  final String? imageUrl;
  final double? rating;
  final List<String> tags;
  final bool isActive;
  final bool inStock;

  factory Product.fromJson(Map<String, dynamic> json) {
    return Product(
      productId: json['product_id'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      price: (json['price'] as num?)?.toDouble(),
      imageUrl: json['image_url'] as String?,
      rating: (json['rating'] as num?)?.toDouble(),
      tags: (json['tags'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
      isActive: json['is_active'] as bool? ?? true,
      inStock: json['in_stock'] as bool? ?? true,
    );
  }
}

class ProductPage {
  const ProductPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.totalPages,
  });

  final List<Product> items;
  final int total;
  final int page;
  final int pageSize;
  final int totalPages;

  factory ProductPage.fromJson(Map<String, dynamic> json) {
    return ProductPage(
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => Product.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: (json['total'] as num?)?.toInt() ?? 0,
      page: (json['page'] as num?)?.toInt() ?? 1,
      pageSize: (json['page_size'] as num?)?.toInt() ?? 20,
      totalPages: (json['total_pages'] as num?)?.toInt() ?? 1,
    );
  }
}

class ProductFilters {
  const ProductFilters({required this.categories, required this.brands});

  final List<String> categories;
  final List<String> brands;

  factory ProductFilters.fromJson(Map<String, dynamic> json) {
    List<String> strings(String key) =>
        (json[key] as List<dynamic>? ?? const []).map((e) => e.toString()).toList();
    return ProductFilters(categories: strings('categories'), brands: strings('brands'));
  }
}

/// What the product list is currently showing (search box + dropdowns + page).
class ProductQuery {
  const ProductQuery({this.search = '', this.category, this.sort = 'name', this.descending = false, this.page = 1});

  final String search;
  final String? category;
  final String sort; // name | price | rating
  final bool descending;
  final int page;

  static const int pageSize = 20;

  /// Changing any filter goes back to page 1 unless a page is given explicitly.
  ProductQuery copyWith({
    String? search,
    String? category,
    bool clearCategory = false,
    String? sort,
    bool? descending,
    int? page,
  }) {
    return ProductQuery(
      search: search ?? this.search,
      category: clearCategory ? null : (category ?? this.category),
      sort: sort ?? this.sort,
      descending: descending ?? this.descending,
      page: page ?? 1,
    );
  }
}
