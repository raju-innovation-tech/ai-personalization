import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/customers_repository.dart';
import '../../domain/customer.dart';

final customersRepositoryProvider = Provider<CustomersRepository>((ref) {
  return CustomersRepository(apiClient: ref.watch(apiClientProvider));
});

final customerQueryProvider = StateProvider<CustomerQuery>((ref) => const CustomerQuery());

final customersPageProvider = FutureProvider.autoDispose<CustomerPage>((ref) async {
  final query = ref.watch(customerQueryProvider);
  return ref.watch(customersRepositoryProvider).fetchPage(query);
});

final customerOverviewProvider = FutureProvider.autoDispose<CustomerOverview>((ref) async {
  return ref.watch(customersRepositoryProvider).fetchOverview();
});

final customerDetailProvider = FutureProvider.autoDispose.family<Customer, String>((ref, id) async {
  return ref.watch(customersRepositoryProvider).fetchCustomer(id);
});

/// Timeline page for one customer: (customer id, page number).
final customerTimelineProvider =
    FutureProvider.autoDispose.family<TimelinePage, (String, int)>((ref, args) async {
  return ref.watch(customersRepositoryProvider).fetchTimeline(args.$1, page: args.$2);
});
