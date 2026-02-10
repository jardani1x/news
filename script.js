(function () {
  const sectionOrder = ["World", "Finance", "Technology", "Local Singapore"];

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
    const allSections = sectionOrder.filter((name) => topics[name]);
    const $grid = $("#news-grid");
    $grid.empty();

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
