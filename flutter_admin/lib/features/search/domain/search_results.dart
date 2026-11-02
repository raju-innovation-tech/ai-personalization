class SearchCustomer {
  const SearchCustomer({required this.id, this.segment});

  final String id;
  final String? segment;
}

class SearchProduct {
  const SearchProduct({required this.id, required this.name, this.category});

  final String id;
  final String name;
  final String? category;
}

class SearchOffer {
  const SearchOffer({required this.id, required this.code, required this.name, required this.status});

  final String id;
  final String code;
  final String name;
  final String status;
}

class SearchResults {
  const SearchResults({required this.customers, required this.products, required this.offers});

  final List<SearchCustomer> customers;
  final List<SearchProduct> products;
  final List<SearchOffer> offers;

  bool get isEmpty => customers.isEmpty && products.isEmpty && offers.isEmpty;

  factory SearchResults.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> rows(String key) =>
        (json[key] as List<dynamic>? ?? const []).map((e) => e as Map<String, dynamic>).toList();

    return SearchResults(
      customers: rows('customers').map((r) => SearchCustomer(id: r['id'] as String, segment: r['segment'] as String?)).toList(),
      products: rows('products')
          .map((r) => SearchProduct(id: r['id'] as String, name: r['name'] as String, category: r['category'] as String?))
          .toList(),
      offers: rows('offers')
          .map((r) => SearchOffer(
                id: r['id'] as String,
                code: r['code'] as String,
                name: r['name'] as String,
                status: r['status'] as String? ?? 'draft',
              ))
          .toList(),
    );
  }
}
