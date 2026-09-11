import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import '../widgets/status_badge.dart';
import '../widgets/tabular_text.dart';
import '../services/api_service.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  bool _isLoading = true;
  String? _errorMessage;

  int _totalProducts = 0;
  double _totalStockValue = 0.0;
  int _expiring30dCount = 0;
  int _expiredCount = 0;
  int _lowStockCount = 0;
  int _outOfStockCount = 0;
  int _deadStockCount = 0;

  int _summaryLoadSeq = 0;

  @override
  void initState() {
    super.initState();
    _loadDashboardSummary();
  }

  Future<void> _loadDashboardSummary() async {
    final currentSeq = ++_summaryLoadSeq;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    debugPrint('[DIAGNOSTIC] InventoryScreen: Fetching lightweight SQL summary [Seq: $currentSeq]');

    try {
      await ApiService.ensureAuthenticated();

      if (currentSeq != _summaryLoadSeq || !mounted) return;

      final data = await ApiService.fetchInventorySummary();

      if (currentSeq != _summaryLoadSeq || !mounted) return;

      setState(() {
        _totalProducts = (data['total_products'] ?? 0) as int;
        _totalStockValue = (data['total_stock_value'] ?? 0.0) as double;
        _expiring30dCount = (data['expiring_30_days'] ?? 0) as int;
        _expiredCount = (data['expired'] ?? 0) as int;
        _lowStockCount = (data['low_stock'] ?? 0) as int;
        _outOfStockCount = (data['out_of_stock'] ?? 0) as int;
        _deadStockCount = (data['dead_stock'] ?? 0) as int;
        _isLoading = false;
        _errorMessage = null;
      });

      debugPrint('[DIAGNOSTIC] DASHBOARD BOUND SUCCESSFULLY -> Total: $_totalProducts, Value: Rs.$_totalStockValue, Low: $_lowStockCount, Expiring: $_expiring30dCount');
    } catch (e) {
      debugPrint('[DIAGNOSTIC] Dashboard summary error: $e');
      if (currentSeq != _summaryLoadSeq || !mounted) return;

      setState(() {
        _isLoading = false;
        _errorMessage = e.toString();
      });
    }
  }

  void _openCategoryDrilldown(String filterKey, String title) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => CategoryMedicinesScreen(
          filterKey: filterKey,
          categoryTitle: title,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surfaceBg,
      appBar: AppBar(
        title: const Text('Inventory Health Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh Summary Metrics',
            onPressed: _loadDashboardSummary,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Calculating live inventory statistics...', style: TextStyle(color: AppColors.textMuted)),
                ],
              ),
            )
          : _errorMessage != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24.0),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.cloud_off_rounded, size: 48, color: AppColors.statusDanger),
                        const SizedBox(height: 12),
                        const Text('Unable to sync inventory summary', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        Text(
                          _errorMessage!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(fontSize: 13, color: AppColors.textMuted),
                        ),
                        const SizedBox(height: 16),
                        ElevatedButton.icon(
                          onPressed: _loadDashboardSummary,
                          icon: const Icon(Icons.refresh, size: 18),
                          label: const Text('Retry Connection'),
                        ),
                      ],
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _loadDashboardSummary,
                  child: ListView(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: _buildKPIHeroCard(
                              'Total Products',
                              _totalProducts.toString(),
                              'Active Items in Store',
                              Icons.inventory_2_outlined,
                              AppColors.brandDeep,
                              onTap: () => _openCategoryDrilldown('all', 'All Active Products'),
                            ),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: _buildKPIHeroCard(
                              'Total Stock Value',
                              '₹${_totalStockValue.toStringAsFixed(2)}',
                              'Inventory Valuation',
                              Icons.account_balance_wallet_outlined,
                              AppColors.statusSafe,
                              onTap: () => _openCategoryDrilldown('all', 'All Active Products'),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.md),

                      const Padding(
                        padding: EdgeInsets.only(left: 4, bottom: 8),
                        child: Text(
                          'Inventory Health & Risk Categories',
                          style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppColors.brandDeep),
                        ),
                      ),

                      _buildCategoryCard(
                        'Expiring in 30 Days',
                        '$_expiring30dCount Medicines',
                        'Near Expiry - Requires Immediate Discount / Return',
                        Icons.hourglass_bottom_rounded,
                        AppColors.statusWarning,
                        onTap: () => _openCategoryDrilldown('expiring_30d', 'Expiring in 30 Days'),
                      ),
                      const SizedBox(height: AppSpacing.xs),

                      _buildCategoryCard(
                        'Expired Stock',
                        '$_expiredCount Medicines',
                        'Past Expiry Date - Unsafe for Sale',
                        Icons.warning_amber_rounded,
                        AppColors.statusDanger,
                        onTap: () => _openCategoryDrilldown('expired', 'Expired Medicines'),
                      ),
                      const SizedBox(height: AppSpacing.xs),

                      _buildCategoryCard(
                        'Low Stock Items',
                        '$_lowStockCount Medicines',
                        '≤10 Units Left - Reorder Threshold Reached',
                        Icons.shopping_cart_checkout_rounded,
                        const Color(0xFFF59E0B),
                        onTap: () => _openCategoryDrilldown('low_stock', 'Low Stock Medicines'),
                      ),
                      const SizedBox(height: AppSpacing.xs),

                      _buildCategoryCard(
                        'Out of Stock',
                        '$_outOfStockCount Medicines',
                        '0 Units Remaining in Pharmacy Stock',
                        Icons.remove_shopping_cart_rounded,
                        const Color(0xFF991B1B),
                        onTap: () => _openCategoryDrilldown('out_of_stock', 'Out of Stock Medicines'),
                      ),
                      const SizedBox(height: AppSpacing.xs),

                      _buildCategoryCard(
                        'Dead Stock (>90 Days)',
                        '$_deadStockCount Medicines',
                        'Zero Sales Velocity Over Past 90 Days',
                        Icons.blur_off_rounded,
                        const Color(0xFF6B21A8),
                        onTap: () => _openCategoryDrilldown('dead_stock', 'Dead Stock Medicines'),
                      ),
                      const SizedBox(height: AppSpacing.md),

                      ListTile(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: const BorderSide(color: AppColors.border),
                        ),
                        tileColor: AppColors.surfaceCard,
                        leading: const Icon(Icons.list_alt_rounded, color: AppColors.brandDeep),
                        title: const Text('View & Search Complete Catalog', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                        subtitle: Text('Browse all $_totalProducts medicines with batch details', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                        trailing: const Icon(Icons.chevron_right_rounded, color: AppColors.brandDeep),
                        onTap: () => _openCategoryDrilldown('all', 'All Active Catalog'),
                      ),
                    ],
                  ),
                ),
    );
  }

  Widget _buildKPIHeroCard(String title, String value, String subtitle, IconData icon, Color color, {VoidCallback? onTap}) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surfaceCard,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.border),
          boxShadow: AppSpacing.shadowSubtle,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: color, size: 20),
            ),
            const SizedBox(height: 10),
            Text(title, style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted, fontWeight: FontWeight.w500)),
            const SizedBox(height: 2),
            Text(
              value,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryCard(String title, String countText, String description, IconData icon, Color color, {required VoidCallback onTap}) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceCard,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
        boxShadow: AppSpacing.shadowSubtle,
      ),
      child: ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        leading: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: color.withOpacity(0.12),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: color, size: 22),
        ),
        title: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(
              child: Text(
                title,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                countText,
                style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold, color: color),
              ),
            ),
          ],
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(description, style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted)),
        ),
        trailing: const Icon(Icons.chevron_right_rounded, size: 20, color: AppColors.textMuted),
      ),
    );
  }
}

/// On-Demand Category Medicine List Screen with True Server-Side Paginated Infinite Scroll
class CategoryMedicinesScreen extends StatefulWidget {
  final String filterKey;
  final String categoryTitle;

  const CategoryMedicinesScreen({
    super.key,
    required this.filterKey,
    required this.categoryTitle,
  });

  @override
  State<CategoryMedicinesScreen> createState() => _CategoryMedicinesScreenState();
}

class _CategoryMedicinesScreenState extends State<CategoryMedicinesScreen> {
  final List<Map<String, dynamic>> _medicines = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  String? _errorMessage;

  int _currentPage = 1;
  int _totalPages = 1;
  int _totalCategoryItems = 0;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    _loadCategoryMedicines();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 300) {
      if (!_isLoadingMore && _currentPage < _totalPages && !_isLoading) {
        _loadMoreCategoryMedicines();
      }
    }
  }

  Future<void> _loadCategoryMedicines() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _currentPage = 1;
    });

    try {
      final res = await ApiService.fetchProductsResponse(
        page: 1,
        limit: 50,
        filter: widget.filterKey,
        search: _searchQuery,
      );

      final List<dynamic> itemsList = res['items'] as List<dynamic>;
      final int totalCount = res['total'] ?? itemsList.length;
      final int totalPg = res['pages'] ?? 1;

      final parsed = <Map<String, dynamic>>[];
      for (var item in itemsList) {
        parsed.add({
          'id': item['id'],
          'name': item['product_name'] ?? 'Unnamed Product',
          'brand': item['brand'] ?? '',
          'category': item['category'] ?? 'General',
          'composition': item['composition'] ?? '',
          'batch': item['batch_number'] ?? 'N/A',
          'quantity': item['quantity'] ?? 0,
          'unit': 'strip',
          'tablets_per_strip': item['tablets_per_strip'] ?? 10,
          'loose_stock': item['loose_tablet_stock'] ?? 0,
          'mrp': (item['unit_price'] ?? 0.0) as num,
          'expiry': item['expiry_date'] ?? 'N/A',
          'days_left': item['days_remaining'] ?? 365,
          'purchase_price': (item['purchase_price'] ?? 0.0) as num,
          'gst_rate': (item['gst_rate'] ?? 12.0) as num,
          'hsn_code': item['hsn_code'] ?? '3004',
        });
      }

      if (!mounted) return;

      setState(() {
        _medicines.clear();
        _medicines.addAll(parsed);
        _totalCategoryItems = totalCount;
        _totalPages = totalPg;
        _currentPage = 1;
        _isLoading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorMessage = e.toString();
        });
      }
    }
  }

  Future<void> _loadMoreCategoryMedicines() async {
    if (_isLoadingMore || _currentPage >= _totalPages) return;

    setState(() {
      _isLoadingMore = true;
    });

    try {
      final nextPage = _currentPage + 1;
      final res = await ApiService.fetchProductsResponse(
        page: nextPage,
        limit: 50,
        filter: widget.filterKey,
        search: _searchQuery,
      );

      final List<dynamic> itemsList = res['items'] as List<dynamic>;

      if (!mounted) return;

      setState(() {
        for (var item in itemsList) {
          _medicines.add({
            'id': item['id'],
            'name': item['product_name'] ?? 'Unnamed Product',
            'brand': item['brand'] ?? '',
            'category': item['category'] ?? 'General',
            'composition': item['composition'] ?? '',
            'batch': item['batch_number'] ?? 'N/A',
            'quantity': item['quantity'] ?? 0,
            'unit': 'strip',
            'tablets_per_strip': item['tablets_per_strip'] ?? 10,
            'loose_stock': item['loose_tablet_stock'] ?? 0,
            'mrp': (item['unit_price'] ?? 0.0) as num,
            'expiry': item['expiry_date'] ?? 'N/A',
            'days_left': item['days_remaining'] ?? 365,
            'purchase_price': (item['purchase_price'] ?? 0.0) as num,
            'gst_rate': (item['gst_rate'] ?? 12.0) as num,
            'hsn_code': item['hsn_code'] ?? '3004',
          });
        }
        _currentPage = nextPage;
        _isLoadingMore = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingMore = false;
        });
      }
    }
  }

  void _showMedicineDetailsSheet(Map<String, dynamic> item) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _MedicineDetailsModalSheet(item: item),
    );
  }

  @override
  Widget build(BuildContext context) {
    final titleText = _isLoading
        ? widget.categoryTitle
        : '${widget.categoryTitle} — ${_totalCategoryItems} medicines';

    return Scaffold(
      appBar: AppBar(
        title: Text(titleText, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search ${widget.categoryTitle.toLowerCase()}...',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          _searchController.clear();
                          setState(() {
                            _searchQuery = '';
                          });
                          _loadCategoryMedicines();
                        },
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              ),
              onSubmitted: (val) {
                setState(() {
                  _searchQuery = val.trim();
                });
                _loadCategoryMedicines();
              },
            ),
          ),

          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _errorMessage != null
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.cloud_off_rounded, size: 44, color: AppColors.statusDanger),
                            const SizedBox(height: 8),
                            Text('Failed to load ${widget.categoryTitle}', style: const TextStyle(fontWeight: FontWeight.bold)),
                            const SizedBox(height: 12),
                            ElevatedButton(onPressed: _loadCategoryMedicines, child: const Text('Retry')),
                          ],
                        ),
                      )
                    : _medicines.isEmpty
                        ? Center(
                            child: Text(
                              'No ${widget.categoryTitle.toLowerCase()} found.',
                              style: const TextStyle(color: AppColors.textMuted),
                            ),
                          )
                        : RefreshIndicator(
                            onRefresh: _loadCategoryMedicines,
                            child: ListView.separated(
                              controller: _scrollController,
                              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.xs),
                              itemCount: _medicines.length + (_isLoadingMore ? 1 : 0),
                              separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.xs),
                              itemBuilder: (ctx, index) {
                                if (index == _medicines.length) {
                                  return const Padding(
                                    padding: EdgeInsets.all(16.0),
                                    child: Center(
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                                          SizedBox(width: 10),
                                          Text('Loading more medicines...', style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
                                        ],
                                      ),
                                    ),
                                  );
                                }
                                final item = _medicines[index];
                                return _buildMedicineCard(item);
                              },
                            ),
                          ),
          ),
        ],
      ),
    );
  }

  Widget _buildMedicineCard(Map<String, dynamic> item) {
    BadgeStatus badgeStatus = BadgeStatus.safe;
    String badgeLabel = 'In Stock';

    if (item['quantity'] <= 0) {
      badgeStatus = BadgeStatus.danger;
      badgeLabel = 'Out of Stock';
    } else if (item['days_left'] <= 0) {
      badgeStatus = BadgeStatus.danger;
      badgeLabel = 'Expired';
    } else if (item['days_left'] <= 30) {
      badgeStatus = BadgeStatus.warning;
      badgeLabel = 'Expiring (${item['days_left']}d)';
    } else if (item['quantity'] <= 10) {
      badgeStatus = BadgeStatus.warning;
      badgeLabel = 'Low Stock';
    }

    return InkWell(
      onTap: () => _showMedicineDetailsSheet(item),
      borderRadius: AppSpacing.roundedMd,
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surfaceCard,
          borderRadius: AppSpacing.roundedMd,
          border: Border.all(color: AppColors.border),
          boxShadow: AppSpacing.shadowSubtle,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item['name'],
                        style: AppTypography.bodyMedium.copyWith(fontWeight: FontWeight.w600),
                      ),
                      if ((item['brand'] as String).isNotEmpty)
                        Text(item['brand'], style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
                    ],
                  ),
                ),
                StatusBadge(label: badgeLabel, status: badgeStatus),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            Row(
              children: [
                BatchBadge(batchNumber: item['batch']),
                const SizedBox(width: AppSpacing.sm),
                Text('Exp: ${item['expiry']}', style: AppTypography.numericDate),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            const Divider(height: 1, color: AppColors.border),
            const SizedBox(height: AppSpacing.sm),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('${item['quantity']} ${item['unit']}s', style: AppTypography.numericPrice),
                TabularCurrency(amount: item['mrp'], style: AppTypography.numericPrice.copyWith(fontSize: 15)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Hardware-accelerated 60/120 FPS Medicine Specification Details Modal Sheet
class _MedicineDetailsModalSheet extends StatefulWidget {
  final Map<String, dynamic> item;

  const _MedicineDetailsModalSheet({required this.item});

  @override
  State<_MedicineDetailsModalSheet> createState() => _MedicineDetailsModalSheetState();
}

class _MedicineDetailsModalSheetState extends State<_MedicineDetailsModalSheet> {
  Map<String, dynamic>? _fullDetails;
  bool _isLoadingExtra = false;

  @override
  void initState() {
    super.initState();
    _loadExtraDetails();
  }

  Future<void> _loadExtraDetails() async {
    final int id = widget.item['id'] as int;
    if (id <= 0) return;

    setState(() {
      _isLoadingExtra = true;
    });

    try {
      final res = await ApiService.fetchProductDetails(id);
      if (mounted && res.isNotEmpty) {
        setState(() {
          _fullDetails = res;
          _isLoadingExtra = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _isLoadingExtra = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final details = _fullDetails ?? item;

    final String name = details['product_name'] ?? item['name'] ?? 'Unnamed Medicine';
    final String brand = details['brand'] ?? item['brand'] ?? 'General';
    final String category = details['category'] ?? item['category'] ?? 'General';
    final String composition = details['composition'] ?? item['composition'] ?? '';
    final String batch = details['batch_number'] ?? item['batch'] ?? 'BATCH-01';
    final String expiry = details['expiry_date'] ?? item['expiry'] ?? '2028-12-31';
    final int daysLeft = details['days_remaining'] ?? item['days_left'] ?? 365;
    final int qty = details['quantity'] ?? item['quantity'] ?? 0;
    final int looseQty = details['loose_tablet_stock'] ?? item['loose_stock'] ?? 0;
    final int tabsPerStrip = details['tablets_per_strip'] ?? item['tablets_per_strip'] ?? 10;
    final num mrp = details['unit_price'] ?? item['mrp'] ?? 0.0;
    final num purchasePrice = details['purchase_price'] ?? item['purchase_price'] ?? 0.0;
    final num gstRate = details['gst_rate'] ?? item['gst_rate'] ?? 12.0;
    final String hsn = details['hsn_code'] ?? item['hsn_code'] ?? '3004';
    final double totalValuation = (qty * mrp).toDouble();

    BadgeStatus badgeStatus = BadgeStatus.safe;
    String badgeLabel = 'In Stock';

    if (qty <= 0) {
      badgeStatus = BadgeStatus.danger;
      badgeLabel = 'Out of Stock';
    } else if (daysLeft <= 0) {
      badgeStatus = BadgeStatus.danger;
      badgeLabel = 'Expired';
    } else if (daysLeft <= 30) {
      badgeStatus = BadgeStatus.warning;
      badgeLabel = 'Expiring (${daysLeft}d)';
    } else if (qty <= 10) {
      badgeStatus = BadgeStatus.warning;
      badgeLabel = 'Low Stock';
    }

    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.surfaceBg,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4.5,
                decoration: BoxDecoration(
                  color: AppColors.border,
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
              const SizedBox(height: 12),

              Padding(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Medicine Specification Details',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.brandDeep),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded, size: 22),
                      onPressed: () => Navigator.pop(context),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1, color: AppColors.border),

              Expanded(
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.all(AppSpacing.md),
                  children: [
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceCard,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Text(
                                  name,
                                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                                ),
                              ),
                              StatusBadge(label: badgeLabel, status: badgeStatus),
                            ],
                          ),
                          if (brand.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text('Manufacturer: $brand', style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
                          ],
                          if (composition.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text('Composition: $composition', style: const TextStyle(fontSize: 12.5, color: AppColors.brandDeep, fontWeight: FontWeight.w500)),
                          ],
                          const SizedBox(height: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: AppColors.brandDeep.withOpacity(0.08),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              'Category: $category',
                              style: const TextStyle(fontSize: 11.5, color: AppColors.brandDeep, fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),

                    const _SectionHeader(title: 'Stock & Inventory Metrics', icon: Icons.inventory_2_outlined),
                    const SizedBox(height: AppSpacing.xs),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceCard,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Column(
                        children: [
                          _DetailRow(label: 'Total Strips Stock', value: '$qty Strips'),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'Loose Tablet Count', value: '$looseQty Units'),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'Tablets Per Strip', value: '$tabsPerStrip Tablets/Strip'),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'Total Units Available', value: '${(qty * tabsPerStrip) + looseQty} Individual Units'),
                        ],
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),

                    const _SectionHeader(title: 'Batch & Expiry Timeline', icon: Icons.hourglass_bottom_rounded),
                    const SizedBox(height: AppSpacing.xs),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceCard,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Column(
                        children: [
                          _DetailRow(label: 'Batch Number', value: batch, isBold: true),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'Expiry Date', value: expiry),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(
                            label: 'Days Remaining',
                            value: '$daysLeft Days',
                            valueColor: daysLeft <= 30 ? AppColors.statusDanger : AppColors.statusSafe,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),

                    const _SectionHeader(title: 'Financial & Tax Valuation', icon: Icons.account_balance_wallet_outlined),
                    const SizedBox(height: AppSpacing.xs),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceCard,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Column(
                        children: [
                          _DetailRow(label: 'Selling Price (MRP)', value: '₹${mrp.toStringAsFixed(2)} / Strip'),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'Purchase Cost Price', value: '₹${purchasePrice.toStringAsFixed(2)} / Strip'),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'Applicable GST Rate', value: '$gstRate%'),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(label: 'HSN Code', value: hsn),
                          const Divider(height: 12, color: AppColors.border),
                          _DetailRow(
                            label: 'Total Stock Valuation',
                            value: '₹${totalValuation.toStringAsFixed(2)}',
                            isBold: true,
                            valueColor: AppColors.brandDeep,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AppSpacing.lg),

                    SizedBox(
                      width: double.infinity,
                      height: 46,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.brandDeep,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                        onPressed: () => Navigator.pop(context),
                        child: const Text('Close Specification Details', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final IconData icon;

  const _SectionHeader({required this.title, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: AppColors.brandDeep),
        const SizedBox(width: 6),
        Text(
          title,
          style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.bold, color: AppColors.brandDeep),
        ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isBold;
  final Color? valueColor;

  const _DetailRow({
    required this.label,
    required this.value,
    this.isBold = false,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted)),
        Text(
          value,
          style: TextStyle(
            fontSize: 13,
            fontWeight: isBold ? FontWeight.bold : FontWeight.w600,
            color: valueColor ?? AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}
