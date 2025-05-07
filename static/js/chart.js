// 创建价格图表
document.addEventListener('DOMContentLoaded', function() {
    try {
        // 获取图表容器
        const priceCtx = document.getElementById('priceChart');
        const volumeCtx = document.getElementById('volumeChart');
        
        if (!priceCtx || !volumeCtx) {
            console.warn('图表容器未找到');
            return;
        }
        
        // 从页面数据属性获取数据
        const stockData = JSON.parse(document.getElementById('stock-data').getAttribute('data-stock'));
        
        if (!stockData || !stockData.prices || !stockData.dates) {
            console.warn('股票数据不完整');
            return;
        }
        
        // 价格图表
        new Chart(priceCtx, {
            type: 'line',
            data: {
                labels: stockData.dates,
                datasets: [{
                    label: stockData.name + ' 收盘价',
                    data: stockData.prices,
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    fill: true,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: stockData.symbol + ' 价格走势'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false
                    }
                }
            }
        });
        
        // 交易量图表
        new Chart(volumeCtx, {
            type: 'bar',
            data: {
                labels: stockData.dates,
                datasets: [{
                    label: '成交量',
                    data: stockData.volumes,
                    backgroundColor: 'rgba(75, 192, 192, 0.5)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: '交易量趋势'
                    }
                }
            }
        });
    } catch (error) {
        console.error('图表加载失败:', error);
    }
}); 