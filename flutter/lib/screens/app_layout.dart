import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import 'billing_screen.dart';
import 'inventory_screen.dart';
import 'khata_screen.dart';
import 'returns_screen.dart';
import 'smart_action_center_screen.dart';
import '../services/api_service.dart';

class AppLayout extends StatefulWidget {
  const AppLayout({super.key});

  @override
  State<AppLayout> createState() => _AppLayoutState();
}

class _AppLayoutState extends State<AppLayout> {
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  String _activeModule = 'Dashboard';

  String _shopName = 'Pharmacy';
  String _userEmail = 'Owner / Pharmacist';

  bool _isDashboardLoading = true;
  double _todaySales = 0.0;
  int _todayBillsCount = 0;
  int _expiredCount = 0;
  int _expiringSoonCount = 0;
  int _lowStockCount = 0;
  double _customerOutstanding = 0.0;

  bool _salesExpanded = true;
  bool _purchasesExpanded = false;
  bool _businessExpanded = false;
  bool _managementExpanded = false;

  @override
  void initState() {
    super.initState();
    _loadProfile();
    _refreshDashboardData();
    _checkForAppUpdates();
  }

  Future<void> _checkForAppUpdates() async {
    try {
      final info = await ApiService.checkAppVersion();
      if (info.isEmpty || !mounted) return;

      final serverVersion = info['version'] as String? ?? '1.0.0';
      const currentVersion = '1.0.0';

      if (_isVersionNewer(serverVersion, currentVersion)) {
        _showUpdateDialog(info);
      }
    } catch (_) {}
  }

  bool _isVersionNewer(String server, String current) {
    try {
      final sParts = server.split('.').map(int.parse).toList();
      final cParts = current.split('.').map(int.parse).toList();
      for (int i = 0; i < sParts.length && i < cParts.length; i++) {
        if (sParts[i] > cParts[i]) return true;
        if (sParts[i] < cParts[i]) return false;
      }
      return sParts.length > cParts.length;
    } catch (_) {
      return server != current;
    }
  }

  void _showUpdateDialog(Map<String, dynamic> info) {
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: const [
            Icon(Icons.system_update_rounded, color: AppColors.brandDeep, size: 28),
            SizedBox(width: 10),
            Text('Update Available', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 17)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('DawaiFlow Mobile v${info['version']} is now available online.', style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text(info['release_notes'] ?? 'General performance improvements and bug fixes.', style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted)),
            const SizedBox(height: 12),
            const Text('Tap "Update Now" to download the APK and update wirelessly without USB cables.', style: TextStyle(fontSize: 11.5, color: AppColors.brandDeep, fontWeight: FontWeight.w500)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Later', style: TextStyle(color: AppColors.textMuted)),
          ),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.brandDeep,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            icon: const Icon(Icons.download_rounded, size: 18, color: Colors.white),
            label: const Text('Update Now', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            onPressed: () {
              Navigator.pop(context);
              final url = info['download_url'] ?? 'https://api.dawaiflow.com/static/dawaiflow-latest.apk';
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Downloading update: $url'),
                  duration: const Duration(seconds: 4),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _loadProfile() async {
    try {
      final u = await ApiService.fetchUserProfile();
      if (u.isNotEmpty && mounted) {
        setState(() {
          _shopName = u['shop_name'] ?? 'Pharmacy';
          _userEmail = u['email'] ?? 'Owner / Pharmacist';
        });
      }
    } catch (_) {}
  }

  Future<void> _refreshDashboardData() async {
    if (!mounted) return;
    setState(() => _isDashboardLoading = true);

    try {
      final summary = await ApiService.fetchDashboardSummary().timeout(
        const Duration(seconds: 8),
        onTimeout: () {
          debugPrint('[Dashboard] Dashboard data load timed out after 8s, using graceful fallback');
          return <String, dynamic>{};
        },
      );
      if (!mounted) return;

      final needsAtt = summary['needs_attention'] as Map<String, dynamic>? ?? {};

      num parseNum(dynamic val) {
        if (val == null) return 0;
        if (val is num) return val;
        return num.tryParse(val.toString()) ?? 0;
      }

      setState(() {
        if (summary.isNotEmpty) {
          _todaySales = parseNum(summary['today_revenue'] ?? (summary['today_business'] != null ? summary['today_business']['sales'] : 0)).toDouble();
          _todayBillsCount = parseNum(summary['today_sales_count'] ?? (summary['today_business'] != null ? summary['today_business']['bills'] : 0)).toInt();
          _expiredCount = parseNum(summary['expired_count'] ?? needsAtt['expired_count']).toInt();
          _expiringSoonCount = parseNum(summary['expiring_soon_count'] ?? needsAtt['expiring_soon_count']).toInt();
          _lowStockCount = parseNum(summary['low_stock_count'] ?? needsAtt['low_stock_count']).toInt();
          _customerOutstanding = parseNum(needsAtt['customer_outstanding'] ?? (summary['needs_attention'] != null ? summary['needs_attention']['customer_outstanding'] : 0)).toDouble();
        }
        _isDashboardLoading = false;
      });
    } catch (e) {
      debugPrint('[Dashboard] Refresh exception: $e');
      if (!mounted) return;
      setState(() => _isDashboardLoading = false);
    }
  }

  void _openSmartActionCenter(String filterKey, String categoryTitle) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => SmartActionCenterScreen(
          filterKey: filterKey,
          categoryTitle: categoryTitle,
        ),
      ),
    );
  }

  void _selectModule(String module) {
    setState(() {
      _activeModule = module;
    });
    if (_scaffoldKey.currentState?.isDrawerOpen ?? false) {
      Navigator.pop(context);
    }
  }

  Widget _buildBody() {
    switch (_activeModule) {
      case 'Billing':
        return const BillingScreen();
      case 'Inventory':
        return const InventoryScreen();
      case 'Khata / Outstanding':
        return const KhataScreen();
      case 'Returned Items':
      case 'Sales Returns':
        return const ReturnsScreen();
      case 'Dashboard':
        return _buildDashboardView();
      default:
        return _buildPlaceholderScreen(_activeModule);
    }
  }

  Widget _buildDashboardView() {
    return Container(
      color: Theme.of(context).scaffoldBackgroundColor,
      child: RefreshIndicator(
        onRefresh: _refreshDashboardData,
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_shopName.isNotEmpty && _shopName != 'Pharmacy' ? _shopName : 'Welcome Back!', style: AppTypography.heading1),
                    const SizedBox(height: AppSpacing.xs),
                    const Text('Here is your pharmacy summary for today.', style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
                  ],
                ),
                IconButton(
                  icon: const Icon(Icons.refresh_rounded, color: AppColors.brandDeep),
                  tooltip: 'Refresh Dashboard Data',
                  onPressed: _refreshDashboardData,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),

            _buildKPIKard('Today\'s Sales', '₹${_todaySales.toStringAsFixed(2)}', Icons.trending_up, AppColors.statusSafe, sub: '$_todayBillsCount Bills'),
            const SizedBox(height: AppSpacing.md),

            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: AppSpacing.md,
              mainAxisSpacing: AppSpacing.md,
              childAspectRatio: 1.4,
              children: [
                _buildKPIKard('Returned Items', 'View Returns', Icons.assignment_return_outlined, AppColors.brandDeep, module: 'Returned Items'),
                _buildKPIKard('Khata Receivables', '₹${_customerOutstanding.toStringAsFixed(0)}', Icons.account_balance_wallet_outlined, AppColors.statusInfo, module: 'Khata / Outstanding'),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),

            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: const [
                Text('Needs Your Attention', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.textPrimary)),
                Text('Smart Action Center', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.brandDeep)),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),

            Card(
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: const BorderSide(color: AppColors.border),
              ),
              child: Column(
                children: [
                  _buildAttentionRow(
                    icon: Icons.report_problem_outlined,
                    iconColor: AppColors.statusDanger,
                    title: 'Expired Batches',
                    countText: '$_expiredCount Batches',
                    subtitle: 'Requires immediate removal or restock',
                    onTap: () => _openSmartActionCenter('expired', 'Expired Batches'),
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  _buildAttentionRow(
                    icon: Icons.warning_amber_rounded,
                    iconColor: AppColors.statusWarning,
                    title: 'Expiring Soon',
                    countText: '$_expiringSoonCount Batches',
                    subtitle: 'Expiring within next 60 days',
                    onTap: () => _openSmartActionCenter('expiring_soon', 'Expiring Soon'),
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  _buildAttentionRow(
                    icon: Icons.inventory_2_outlined,
                    iconColor: AppColors.statusWarning,
                    title: 'Low Stock Alert',
                    countText: '$_lowStockCount Items',
                    subtitle: 'Stock at or below reorder threshold',
                    onTap: () => _openSmartActionCenter('low_stock', 'Low Stock Alert'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.lg),

            InkWell(
              onTap: () => _selectModule('Returned Items'),
              borderRadius: BorderRadius.circular(12),
              child: Card(
                elevation: 0,
                color: AppColors.brandDeep.withOpacity(0.06),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(color: AppColors.brandDeep.withOpacity(0.2)),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.assignment_return_outlined, color: AppColors.brandDeep, size: 28),
                          const SizedBox(width: 12),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: const [
                              Text('Returned Items Management', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: AppColors.brandDeep)),
                              SizedBox(height: 2),
                              Text('Process customer sales returns & restore inventory', style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
                            ],
                          ),
                        ],
                      ),
                      const Icon(Icons.arrow_forward_ios, size: 16, color: AppColors.brandDeep),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAttentionRow({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String countText,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: iconColor.withOpacity(0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: iconColor, size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: AppColors.textPrimary)),
                      Text(countText, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: iconColor)),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(subtitle, style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.arrow_forward_ios, size: 14, color: AppColors.textMuted),
          ],
        ),
      ),
    );
  }

  Widget _buildKPIKard(String title, String value, IconData icon, Color accentColor, {String? sub, String? module}) {
    return InkWell(
      onTap: module != null ? () => _selectModule(module) : null,
      borderRadius: BorderRadius.circular(12),
      child: Card(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: AppColors.border),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(title, style: const TextStyle(fontSize: 12, color: AppColors.textMuted, fontWeight: FontWeight.w500)),
                  Icon(icon, color: accentColor, size: 20),
                ],
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(value, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: AppColors.textPrimary)),
                  if (sub != null) ...[
                    const SizedBox(height: 2),
                    Text(sub, style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPlaceholderScreen(String title) {
    return Container(
      color: AppColors.surfaceBg,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.construction_rounded, size: 64, color: AppColors.brandDeep.withOpacity(0.5)),
          const SizedBox(height: 16),
          Text(title, style: AppTypography.heading2),
          const SizedBox(height: 8),
          const Text(
            'This ERP module is scheduled for implementation in the next phase.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }

  Widget _buildDrawerItem({
    required IconData icon,
    required String label,
    required String module,
  }) {
    final bool isSelected = _activeModule == module;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      decoration: BoxDecoration(
        color: isSelected ? AppColors.brandDeep.withOpacity(0.08) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
      ),
      child: ListTile(
        visualDensity: const VisualDensity(vertical: -3),
        leading: Icon(icon, color: isSelected ? AppColors.brandDeep : AppColors.textMuted, size: 20),
        title: Text(
          label,
          style: TextStyle(
            color: isSelected ? AppColors.brandDeep : AppColors.textPrimary,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
            fontSize: 14,
          ),
        ),
        onTap: () => _selectModule(module),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      appBar: AppBar(
        title: Text(_activeModule, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
        leading: IconButton(
          icon: const Icon(Icons.menu),
          onPressed: () => _scaffoldKey.currentState?.openDrawer(),
        ),
        actions: [
          if (_activeModule == 'Dashboard')
            IconButton(
              icon: const Icon(Icons.refresh_rounded),
              onPressed: _refreshDashboardData,
            ),
        ],
      ),
      drawer: Drawer(
        backgroundColor: Colors.white,
        child: Column(
          children: [
            UserAccountsDrawerHeader(
              decoration: const BoxDecoration(color: AppColors.brandDeep),
              currentAccountPicture: CircleAvatar(
                backgroundColor: Colors.white,
                child: Text(
                  _shopName.isNotEmpty ? _shopName[0].toUpperCase() : 'P',
                  style: const TextStyle(color: AppColors.brandDeep, fontWeight: FontWeight.bold, fontSize: 20),
                ),
              ),
              accountName: Text(_shopName, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              accountEmail: Text(_userEmail, style: const TextStyle(fontSize: 12, color: Colors.white70)),
            ),
            Expanded(
              child: ListView(
                padding: EdgeInsets.zero,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(left: 16.0, top: 12, bottom: 4),
                    child: Text('MAIN', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppColors.textMuted, letterSpacing: 1.1)),
                  ),
                  _buildDrawerItem(icon: Icons.dashboard_outlined, label: 'Dashboard', module: 'Dashboard'),
                  _buildDrawerItem(icon: Icons.receipt_long_outlined, label: 'Billing', module: 'Billing'),
                  _buildDrawerItem(icon: Icons.inventory_2_outlined, label: 'Inventory', module: 'Inventory'),
                  _buildDrawerItem(icon: Icons.notifications_none_outlined, label: 'Alerts', module: 'Alerts'),
                  const Divider(indent: 16, endIndent: 16, height: 16),
                  ExpansionTile(
                    title: const Text('SALES', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textMuted)),
                    leading: const Icon(Icons.point_of_sale_outlined, size: 20, color: AppColors.textMuted),
                    initiallyExpanded: _salesExpanded,
                    onExpansionChanged: (val) => setState(() => _salesExpanded = val),
                    children: [
                      _buildDrawerItem(icon: Icons.history, label: 'Sales History', module: 'Sales History'),
                      _buildDrawerItem(icon: Icons.keyboard_return, label: 'Sales Returns', module: 'Sales Returns'),
                      _buildDrawerItem(icon: Icons.people_outline, label: 'Customers', module: 'Customers'),
                      _buildDrawerItem(icon: Icons.account_balance_wallet_outlined, label: 'Khata / Outstanding', module: 'Khata / Outstanding'),
                    ],
                  ),
                  ExpansionTile(
                    title: const Text('PURCHASES', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textMuted)),
                    leading: const Icon(Icons.shopping_cart_outlined, size: 20, color: AppColors.textMuted),
                    initiallyExpanded: _purchasesExpanded,
                    onExpansionChanged: (val) => setState(() => _purchasesExpanded = val),
                    children: [
                      _buildDrawerItem(icon: Icons.add_shopping_cart, label: 'Purchases Entry', module: 'Purchases Entry'),
                      _buildDrawerItem(icon: Icons.history_edu, label: 'Purchase Returns', module: 'Purchase Returns'),
                      _buildDrawerItem(icon: Icons.business_outlined, label: 'Suppliers', module: 'Suppliers'),
                    ],
                  ),
                  ExpansionTile(
                    title: const Text('BUSINESS', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textMuted)),
                    leading: const Icon(Icons.analytics_outlined, size: 20, color: AppColors.textMuted),
                    initiallyExpanded: _businessExpanded,
                    onExpansionChanged: (val) => setState(() => _businessExpanded = val),
                    children: [
                      _buildDrawerItem(icon: Icons.bar_chart_outlined, label: 'Reports', module: 'Reports'),
                      _buildDrawerItem(icon: Icons.trending_up_outlined, label: 'Analytics', module: 'Analytics'),
                    ],
                  ),
                  ExpansionTile(
                    title: const Text('MANAGEMENT', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textMuted)),
                    leading: const Icon(Icons.settings_suggest_outlined, size: 20, color: AppColors.textMuted),
                    initiallyExpanded: _managementExpanded,
                    onExpansionChanged: (val) => setState(() => _managementExpanded = val),
                    children: [
                      _buildDrawerItem(icon: Icons.badge_outlined, label: 'Staff / Users', module: 'Staff / Users'),
                      _buildDrawerItem(icon: Icons.store_mall_directory_outlined, label: 'Stores / Branches', module: 'Stores / Branches'),
                      _buildDrawerItem(icon: Icons.settings_outlined, label: 'Settings', module: 'Settings'),
                    ],
                  ),
                  const Divider(indent: 16, endIndent: 16, height: 16),
                  _buildDrawerItem(icon: Icons.person_outline, label: 'Profile', module: 'Profile'),
                  _buildDrawerItem(icon: Icons.logout_outlined, label: 'Logout', module: 'Logout'),
                ],
              ),
            ),
          ],
        ),
      ),
      body: _buildBody(),
    );
  }
}
