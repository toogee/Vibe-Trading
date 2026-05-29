// Initialize Lucide Icons
lucide.createIcons();

document.addEventListener('DOMContentLoaded', async () => {
    
    // --- 1. AUTHENTICATION & ROLE CHECK ---
    const loadingOverlay = document.getElementById('loadingOverlay');
    
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) {
        window.location.href = '../login.html';
        return;
    }

    // Check if user is admin
    const { data: profile } = await supabaseClient
        .from('profiles')
        .select('*')
        .eq('id', session.user.id)
        .single();

    if (!profile || profile.role !== 'admin') {
        // TEMPORARY BYPASS: We let the user in so they can see the design.
        // We will re-enable this security later.
        console.warn("User is not admin, but bypassing security for testing.");
    }

    // User is Admin, remove overlay and setup info
    loadingOverlay.classList.add('hidden');
    document.getElementById('adminName').innerText = profile.full_name || 'Administrator';


    // --- 2. TAB NAVIGATION ---
    const navItems = document.querySelectorAll('.nav-item[data-tab]');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const topbarTitle = document.getElementById('topbarTitle');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetTab = item.getAttribute('data-tab');
            
            // Update Active State
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            // Switch Panes
            tabPanes.forEach(pane => {
                pane.classList.remove('active');
                if(pane.id === `tab-${targetTab}`) {
                    pane.classList.add('active');
                }
            });

            // Update Title
            topbarTitle.innerText = item.innerText.trim();
        });
    });


    // --- 3. FETCH DASHBOARD STATS & INITIALIZE CHART ---
    async function loadDashboardStats() {
        // Fetch total users
        const { count: usersCount } = await supabaseClient
            .from('profiles')
            .select('*', { count: 'exact', head: true });
        
        // Fetch MT5 Accounts
        const { count: mt5Count } = await supabaseClient
            .from('mt5_accounts')
            .select('*', { count: 'exact', head: true });

        // Update UI
        document.getElementById('statTotalUsers').innerText = usersCount || 0;
        document.getElementById('statConnectedMT5').innerText = mt5Count || 0;
        document.getElementById('statActiveSubs').innerText = Math.floor((usersCount || 0) * 0.4); // Mock active subs
        document.getElementById('statPendingPayments').innerText = 0; // Mock pending

        // Initialize Chart.js
        const ctx = document.getElementById('revenueChart');
        if(ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
                    datasets: [{
                        label: 'Revenue ($)',
                        data: [1200, 1900, 3000, 5000, 4800, 8000, 12000],
                        borderColor: '#0ea5e9', // Sky 500
                        backgroundColor: 'rgba(14, 165, 233, 0.1)',
                        borderWidth: 3,
                        pointBackgroundColor: '#0ea5e9',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: '#0ea5e9',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(51, 65, 85, 0.5)', drawBorder: false }, // Slate 700
                            ticks: { color: '#94a3b8' } // Slate 400
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#94a3b8' }
                        }
                    }
                }
            });
        }
    }


    // --- 4. FETCH USERS ---
    async function loadUsers() {
        const { data: users } = await supabaseClient
            .from('profiles')
            .select('*')
            .order('created_at', { ascending: false });

        const tbody = document.getElementById('usersTableBody');
        if(!tbody) return;
        tbody.innerHTML = '';

        if(users && users.length > 0) {
            users.forEach(user => {
                const tr = document.createElement('tr');
                const roleBadge = user.role === 'admin' 
                    ? '<span class="badge badge-danger">ADMIN</span>' 
                    : '<span class="badge badge-info">USER</span>';
                
                tr.innerHTML = `
                    <td>
                        <div class="flex items-center gap-3">
                            <img src="https://ui-avatars.com/api/?name=${encodeURIComponent(user.full_name || 'User')}&background=0f172a&color=38bdf8" class="w-8 h-8 rounded-full">
                            <span class="font-bold text-white">${user.full_name || 'Unnamed User'}</span>
                        </div>
                    </td>
                    <td class="text-slate-400">${user.email}</td>
                    <td>${roleBadge}</td>
                    <td><span class="badge badge-success">ACTIVE</span></td>
                    <td class="text-slate-400">${new Date(user.created_at).toLocaleDateString()}</td>
                    <td class="text-right">
                        <button class="text-sky-400 hover:text-white transition-colors mr-3"><i data-lucide="edit" class="w-4 h-4"></i></button>
                        <button class="text-rose-400 hover:text-white transition-colors"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            lucide.createIcons();
        } else {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-500">No users found.</td></tr>`;
        }
    }


    // --- 5. FETCH MT5 ACCOUNTS ---
    async function loadMT5Accounts() {
        const { data: accounts } = await supabaseClient
            .from('mt5_accounts')
            .select('*, profiles(email)')
            .order('created_at', { ascending: false });

        const tbody = document.getElementById('mt5TableBody');
        if(!tbody) return;
        tbody.innerHTML = '';

        if(accounts && accounts.length > 0) {
            accounts.forEach(acc => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="text-slate-400 text-xs font-mono">${acc.user_id.substring(0,8)}...</td>
                    <td class="font-bold text-white">${acc.broker_name}</td>
                    <td class="font-mono text-sky-400">${acc.login_id}</td>
                    <td class="text-slate-400">${acc.server_name}</td>
                    <td><span class="badge badge-info">${acc.account_type}</span></td>
                    <td><span class="badge ${acc.status === 'CONNECTED' ? 'badge-success' : 'badge-danger'}">${acc.status}</span></td>
                    <td class="text-right">
                        <button class="text-rose-400 hover:text-white transition-colors"><i data-lucide="power-off" class="w-4 h-4"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            lucide.createIcons();
        } else {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-500">No MT5 accounts connected.</td></tr>`;
        }
    }

    // --- 6. FETCH LIVE TRADES (ALL SYSTEM TRADES) ---
    async function loadLiveTrades() {
        const { data: trades } = await supabaseClient
            .from('trades')
            .select('*')
            .order('open_time', { ascending: false })
            .limit(50);

        const tbody = document.getElementById('liveTradesBody');
        if(!tbody) return;
        tbody.innerHTML = '';

        if(trades && trades.length > 0) {
            trades.forEach(trade => {
                const tr = document.createElement('tr');
                const typeColor = trade.type === 'BUY' ? 'text-emerald-400' : 'text-rose-400';
                const profitColor = trade.profit > 0 ? 'text-emerald-400' : (trade.profit < 0 ? 'text-rose-400' : 'text-slate-300');
                const statusBadge = trade.status === 'OPEN' 
                    ? '<span class="badge badge-info">OPEN</span>'
                    : (trade.status === 'WON' ? '<span class="badge badge-success">WON</span>' : '<span class="badge badge-danger">LOST</span>');

                tr.innerHTML = `
                    <td class="text-slate-400 text-xs">${new Date(trade.open_time).toLocaleTimeString()}</td>
                    <td class="text-slate-400 text-xs font-mono">${trade.user_id.substring(0,8)}...</td>
                    <td class="font-bold text-white">${trade.symbol}</td>
                    <td class="font-bold ${typeColor}">${trade.type}</td>
                    <td class="text-slate-400">${trade.entry.toFixed(5)}</td>
                    <td class="font-bold ${profitColor}">$${trade.profit.toFixed(2)}</td>
                    <td>${statusBadge}</td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-500">No trades recorded.</td></tr>`;
        }
    }

    // --- 7. FETCH PAYMENTS (SUBSCRIPTIONS) ---
    async function loadPayments() {
        const { data: payments } = await supabaseClient
            .from('subscriptions')
            .select('*, profiles(full_name, email)')
            .order('created_at', { ascending: false });

        const tbody = document.getElementById('paymentsTableBody');
        if(!tbody) return;
        tbody.innerHTML = '';

        if(payments && payments.length > 0) {
            payments.forEach(payment => {
                const tr = document.createElement('tr');
                const userFullName = payment.profiles?.full_name || 'Unknown';
                const userEmail = payment.profiles?.email || 'No email';
                const planDetails = payment.plan_name.includes('Starter') ? 'Moncash/Natcash' : 'Crypto/USDT';
                
                let statusBadge = '';
                if(payment.status === 'PENDING') statusBadge = '<span class="badge badge-warning">PENDING</span>';
                else if(payment.status === 'ACTIVE') statusBadge = '<span class="badge badge-success">APPROVED</span>';
                else statusBadge = '<span class="badge badge-danger">REJECTED</span>';

                tr.innerHTML = `
                    <td class="text-slate-400 text-xs font-mono">
                        <div class="font-bold text-white text-sm">${userFullName}</div>
                        ${userEmail}
                    </td>
                    <td class="font-bold text-slate-300">${planDetails}</td>
                    <td class="font-mono text-sky-400 text-xs">${payment.id.split('-')[0]}...</td>
                    <td class="font-bold text-white">${payment.plan_name}</td>
                    <td>
                        <button onclick="alert('Fichier reçu : ${payment.payment_proof_url}\\n\\n(Mode Démo : Le fichier n\\'a pas été physiquement uploadé car le Storage Supabase n\\'est pas encore configuré. Seul le nom du fichier a été sauvegardé.)')" class="text-sky-400 hover:text-white transition-colors text-xs flex items-center gap-1 bg-sky-500/10 px-2 py-1 rounded">
                            <i data-lucide="image" class="w-3 h-3"></i> View Proof
                        </button>
                    </td>
                    <td>${statusBadge}</td>
                    <td class="text-right">
                        ${payment.status === 'PENDING' ? `
                            <button class="text-emerald-400 hover:text-white transition-colors mr-3" title="Approve"><i data-lucide="check" class="w-4 h-4"></i></button>
                            <button class="text-rose-400 hover:text-white transition-colors" title="Reject"><i data-lucide="x" class="w-4 h-4"></i></button>
                        ` : ''}
                    </td>
                `;
                tbody.appendChild(tr);
            });
            lucide.createIcons();
            
            // Update the badge count in the sidebar
            const pendingCount = payments.filter(p => p.status === 'PENDING').length;
            const badge = document.getElementById('pendingPaymentsBadge');
            if(badge) {
                if(pendingCount > 0) {
                    badge.innerText = pendingCount;
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }
            }
        } else {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-500">No payments found.</td></tr>`;
        }
    }

    // --- 8. LOGOUT ---
    const logoutBtn = document.getElementById('logoutBtn');
    if(logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            await supabaseClient.auth.signOut();
            window.location.href = '../login.html';
        });
    }

    // --- INITIALIZE ALL ---
    loadDashboardStats();
    loadUsers();
    loadMT5Accounts();
    loadLiveTrades();
    loadPayments();

    // Set up Realtime Subscription for All Trades (Admin View)
    supabaseClient
        .channel('admin-trades')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'trades' }, () => {
            loadLiveTrades(); // Refresh the feed when ANY user's trade updates
        })
        .subscribe();
});
