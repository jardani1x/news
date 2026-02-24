(function () {
  const sectionOrder = ["World", "Finance", "Technology", "Crypto", "Markets", "Singapore", "US Politics", "Science", "top10"];

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function render(data) {
    $("#updated").text(`Updated: ${data.updated_sgt || "N/A"}`);

    // Handle both old format (topics) and new format (categories)
    const topics = data.categories || data.topics || {};
    const top10 = data.top10 || [];
    const charts = data.charts || {};
    
    // Add charts section if available
    let chartHtml = '';
    if (charts.world_indices || charts.crypto) {
      chartHtml = `
        <section class="section card charts-section">
          <h2>📈 Live Charts</h2>
          <div class="charts-grid">
            ${charts.world_indices ? `<div class="chart-container"><iframe src="charts/${charts.world_indices}" width="100%" height="400"></iframe></div>` : ''}
            ${charts.crypto ? `<div class="chart-container"><iframe src="charts/${charts.crypto}" width="100%" height="400"></iframe></div>` : ''}
          </div>
        </section>
      `;
    }
    
    // Add top 10 if available
    let top10Html = '';
    if (top10.length > 0) {
      const list = top10
        .map((item) => {
          const title = escapeHtml(item.title || "Untitled");
          const source = escapeHtml(item.source || "Source");
          const published = escapeHtml(item.published || "");
          const link = escapeHtml(item.link || "#");
          return `
            <li class="news-item">
              <a href="${link}" target="_blank" rel="noopener noreferrer">${title}</a>
              <div class="meta">${source}${published ? ` • ${published}` : ""}</div>
            </li>
          `;
        })
        .join("");
      
      top10Html = `
        <section class="section card">
          <h2>🔥 Top 10 Headlines</h2>
          <ul class="news-list">${list}</ul>
        </section>
      `;
    }

    const allSections = sectionOrder.filter((name) => topics[name] && topics[name].length > 0);
    const $grid = $("#news-grid");
    $grid.empty();

    // Add charts first
    if (chartHtml) $grid.append(chartHtml);
    
    // Add top 10
    if (top10Html) $grid.append(top10Html);

    // Add category sections
    allSections.forEach((name) => {
      const items = topics[name] || [];
      const list = items
        .map((item) => {
          const title = escapeHtml(item.title || "Untitled");
          const source = escapeHtml(item.source || "Source");
          const published = escapeHtml(item.published || "");
          const link = escapeHtml(item.link || "#");
          return `
            <li class="news-item">
              <a href="${link}" target="_blank" rel="noopener noreferrer">${title}</a>
              <div class="meta">${source}${published ? ` • ${published}` : ""}</div>
            </li>
          `;
        })
        .join("");

      $grid.append(`
        <section class="section card">
          <h2>${escapeHtml(name)}</h2>
          <ul class="news-list">${list || "<li class='status'>No items</li>"}</ul>
        </section>
      `);
    });
  }

  function showError(message) {
    $("#news-grid").html(`<p class="status">${escapeHtml(message)}</p>`);
  }

  $.getJSON("data/news.json")
    .done(render)
    .fail(() => showError("Could not load news data. Run the refresh script and redeploy."));
})();
