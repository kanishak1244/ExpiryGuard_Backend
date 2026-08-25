import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import 'billing_screen.dart';
import 'inventory_screen.dart';
import 'khata_screen.dart';

class AppLayout extends StatefulWidget {
  const AppLayout({super.key});

  @override
  State<AppLayout> createState() => _AppLayoutState();
}

class _AppLayoutState extends State<AppLayout> {
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  String _activeModule = 'Dashboard';

  // State to manage collapsible drawer sections
  bool _salesExpanded = true;
  bool _purchasesExpanded = false;
  bool _businessExpanded = false;
  bool _managementExpanded = false;

  void _selectModule(String module) {
    setState(() {
      _activeModule = module;
    });
    // Close drawer
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
      case 'Dashboard':
        return _buildDashboardMockView();
      default:
        return _buildPlaceholderScreen(_activeModule);
    }
  }

  Widget _buildDashboardMockView() {
    return Container(
      color: AppColors.surfaceBg,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: ListView(
        children: [
          Text('Welcome Back, Kanishak!', style: AppTypography.heading1),
          const SizedBox(height: AppSpacing.sm),
          const Text('Here is your pharmacy summary for today.', style: TextStyle(color: AppColors.textMuted)),
          const SizedBox(height: AppSpacing.lg),
          
          // Bento KPI grid
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: AppSpacing.md,
            mainAxisSpacing: AppSpacing.md,
            childAspectRatio: 1.3,
            children: [
              _buildKPIKard('Today\'s Sales', '₹12,450', Icons.trending_up, AppColors.statusSafe),
              _buildKPIKard('Net Profit', '₹3,735', Icons.pie_chart, AppColors.statusInfo),
              _buildKPIKard('Low Stock Alert', '12 items', Icons.warning_amber_rounded, AppColors.statusWarning),
              _buildKPIKard('Expired Value', '₹4,500', Icons.report_problem, AppColors.statusDanger),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          
          // Outstanding section
          _buildKPIKard(
            'Khata Credit Receivables', 
            '₹8,250 Outstanding', 
            Icons.account_balance_wallet_outlined, 
            AppColors.brandDeep,
            fullWidth: true
          ),
        ],
      ),
    );
  }

  Widget _buildKPIKard(String title, String value, IconData icon, Color accentColor, {bool fullWidth = false}) {
    return Card(
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
            Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppColors.textPrimary)),
          ],
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
              icon: const Icon(Icons.notifications_none),
              onPressed: () {},
            ),
          if (_activeModule == 'Inventory')
            IconButton(
              icon: const Icon(Icons.search),
              onPressed: () {},
            ),
        ],
      ),
      drawer: Drawer(
        backgroundColor: Colors.white,
        child: Column(
          children: [
            // Premium Header Section
            UserAccountsDrawerHeader(
              decoration: const BoxDecoration(color: AppColors.brandDeep),
              currentAccountPicture: const CircleAvatar(
                backgroundColor: Colors.white,
                child: Text('EG', style: TextStyle(color: AppColors.brandDeep, fontWeight: FontWeight.bold, fontSize: 20)),
              ),
              accountName: const Text('ExpiryGuard', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              accountEmail: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Apollo Pharmacy — Delhi', style: TextStyle(fontSize: 12, color: Colors.white70)),
                  Text('Kanishak • Owner', style: TextStyle(fontSize: 12, color: Colors.white70)),
                ],
              ),
            ),
            
            // Scrollable Menu List
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
                  
                  // Collapsible SALES section
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
                  
                  // Collapsible PURCHASES section
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

                  // Collapsible BUSINESS section
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

                  // Collapsible MANAGEMENT section
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
