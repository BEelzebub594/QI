// 主JavaScript文件

// 等待页面完全加载
document.addEventListener('DOMContentLoaded', function() {
    console.log('巨硬工作室量化分析平台已加载');
    
    // 为所有的卡片添加悬停动画效果
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
    
    // 为表格行添加点击事件
    const tableRows = document.querySelectorAll('tbody tr');
    tableRows.forEach(row => {
        row.style.cursor = 'pointer';
        
        row.addEventListener('click', function(e) {
            // 如果点击的是按钮，不处理
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.closest('button') || e.target.closest('a')) {
                return;
            }
            
            // 获取第一个单元格中的链接
            const link = this.querySelector('td:first-child a');
            if (link) {
                window.location.href = link.href;
            }
        });
    });
    
    // 初始化工具提示
    initTooltips();
    
    // 为搜索表单添加处理函数
    initSearchForm();
});

// 初始化工具提示
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// 初始化搜索表单
function initSearchForm() {
    const searchForm = document.querySelector('form.d-flex');
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const searchInput = this.querySelector('input[type="search"]');
            const searchValue = searchInput.value.trim();
            
            if (searchValue) {
                // 在实际应用中，这里会是一个AJAX请求或页面跳转
                alert(`搜索股票: ${searchValue}`);
                // window.location.href = `/search?q=${encodeURIComponent(searchValue)}`;
            }
        });
    }
}

// 格式化数字为带千位分隔符的格式
function formatNumber(num) {
    return num.toString().replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1,');
}

// 格式化百分比
function formatPercent(num) {
    return (num > 0 ? '+' : '') + num.toFixed(2) + '%';
}

// 模拟API调用函数
function fetchStockData(symbol, callback) {
    // 模拟API延迟
    setTimeout(() => {
        // 模拟数据
        const data = {
            symbol: symbol,
            name: `${symbol} 公司`,
            price: 120.45 + (Math.random() * 10 - 5),
            change: 2.3 + (Math.random() * 2 - 1),
            volume: 3245678 + (Math.random() * 1000000 - 500000),
            market_cap: "1.2T",
            pe_ratio: 22.5 + (Math.random() * 5 - 2.5)
        };
        
        callback(data);
    }, 500);
} 