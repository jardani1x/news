(function () {
  const sectionOrder = ["World", "US", "Technology", "War & Military", "Finance", "Singapore"];

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

    const topics = data.topics || {};
    const $grid = $("#news-grid");
    $grid.empty();

    sectionOrder.forEach(name => {
      const items = topics[name] || [];
      if (!items.length) return;
      
      const list = items
        .map(item => {
          const title = escapeHtml(item.title || "Untitled");
          const source = escapeHtml(item.source || "Source");
          const link = escapeHtml(item.link || "#");
          return `
            <li class="news-item">
              <a href="${link}" target="_blank" rel="noopener">${title}</a>
              <div class="meta">${source}</div>
            </li>
          `;
        })
        .join("");

      $grid.append(`
        <section class="section card">
          <h2>${escapeHtml(name)}</h2>
          <ul class="news-list">${list}</ul>
        </section>
      `);
    });
  }

  function showError(msg) {
    $("#news-grid").html(`<p class="status">${escapeHtml(msg)}</p>`);
  }

  $.getJSON("data/news.json")
    .done(render)
    .fail(() => showError("Could not load news. Run build_news.py and redeploy."));
})();
