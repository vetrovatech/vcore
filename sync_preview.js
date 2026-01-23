    }

function syncProducts(incremental = true) {
    if (incremental) {
        // For incremental sync, first fetch and show changed products
        fetch('/api/wordpress/changed-products')
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    alert('Error fetching changed products: ' + (data.message || 'Unknown error'));
                    return;
                }

                if (data.count === 0) {
                    alert('✅ All products are up to date!\\n\\nNo products need syncing.');
                    return;
                }

                // Build product list for confirmation
                let productList = data.products.slice(0, 10).map(p =>
                    `  • ${p.name} (${p.category})`
                ).join('\\n');

                if (data.count > 10) {
                    productList += `\\n  ... and ${data.count - 10} more`;
                }

                const confirmed = confirm(
                    `📋 Products to Sync: ${data.count}\\n\\n` +
                    productList + '\\n\\n' +
                    `⏱️ Estimated Time: ${data.count < 5 ? '1-2' : '2-5'} minutes\\n\\n` +
                    'Do you want to sync these products?'
                );

                if (confirmed) {
                    performSync(incremental, data.count);
                }
            })
            .catch(error => {
                alert('Error: ' + error.message);
            });
    } else {
        // For full sync, show standard confirmation
        const confirmed = confirm(
            `⚠️ WordPress Full Sync\\n\\n` +
            'This will sync ALL 74 products to WordPress.\\n\\n' +
            `⏱️ Estimated Time: 10-15 minutes\\n\\n` +
            'Do you want to continue?'
        );

        if (confirmed) {
            performSync(incremental, 74);
        }
    }
}

function performSync(incremental, productCount) {
    const syncType = incremental ? 'Quick Sync' : 'Full Sync';
    const timeEstimate = productCount < 5 ? '1-2 minutes' : (incremental ? '2-5 minutes' : '10-15 minutes');

    const syncBtnId = incremental ? 'sync-btn-incremental' : 'sync-btn-full';
    const syncBtn = document.getElementById(syncBtnId);
    const progressCard = document.getElementById('progress-card');
    const syncProgress = document.getElementById('sync-progress');
    const progressText = document.getElementById('progress-text');
    const syncStatus = document.getElementById('sync-status');

    // Disable both buttons during sync
    document.getElementById('sync-btn-incremental').disabled = true;
    document.getElementById('sync-btn-full').disabled = true;

    syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
    progressCard.style.display = 'block';

    // Simulate progress
    let progress = 0;
    const progressInterval = setInterval(() => {
        progress += 5;
        if (progress <= 90) {
            syncProgress.style.width = progress + '%';
            progressText.textContent = progress + '%';
        }
    }, 1000);

    syncStatus.innerHTML = `<p><i class="fas fa-spinner fa-spin"></i> Syncing ${productCount} product${productCount > 1 ? 's' : ''}... Please wait, this may take ${timeEstimate}.</p>`;

    fetch('/api/wordpress/sync-all', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ incremental: incremental })
    })
        .then(response => response.json())
        .then(data => {
            clearInterval(progressInterval);
            syncProgress.style.width = '100%';
            progressText.textContent = '100%';

            setTimeout(() => {
                progressCard.style.display = 'none';

                // Re-enable buttons
                document.getElementById('sync-btn-incremental').disabled = false;
                document.getElementById('sync-btn-full').disabled = false;
                document.getElementById('sync-btn-incremental').innerHTML = '<i class="fas fa-sync-alt"></i> Quick Sync';
                document.getElementById('sync-btn-full').innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Full Sync';

                showResults(data, `${syncType} Complete`);

                // Refresh stats
                location.reload();
            }, 1000);
        })
        .catch(error => {
            clearInterval(progressInterval);
            progressCard.style.display = 'none';

            // Re-enable buttons
            document.getElementById('sync-btn-incremental').disabled = false;
            document.getElementById('sync-btn-full').disabled = false;
            document.getElementById('sync-btn-incremental').innerHTML = '<i class="fas fa-sync-alt"></i> Quick Sync';
            document.getElementById('sync-btn-full').innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Full Sync';

            showResults({ success: false, message: error.message }, `${syncType} Failed`);
        });
}
