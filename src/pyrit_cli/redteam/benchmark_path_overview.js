/* Aggregate Sankey (d3-sankey + d3) for benchmark HTML reports. */
(function () {
  var jsonEl = document.getElementById("bench-path-overview-json");
  var svgEl = document.getElementById("path-overview-sankey-svg");
  if (!jsonEl || !svgEl || typeof d3 === "undefined") return;

  var sankeyFactory = typeof d3.sankey === "function" ? d3.sankey : null;
  var linkHorizontal =
    typeof d3.sankeyLinkHorizontal === "function" ? d3.sankeyLinkHorizontal : null;
  if (!sankeyFactory || !linkHorizontal) return;

  var data;
  try {
    data = JSON.parse(jsonEl.textContent);
  } catch (e) {
    return;
  }

  var S = (data && data.sankey) || { nodes: [], links: [] };
  var nodes = S.nodes || [];
  var links = S.links || [];
  if (!nodes.length) {
    d3.select(svgEl.parentElement)
      .append("p")
      .attr("class", "meta")
      .text("No aggregate flow data for this run.");
    return;
  }
  if (!links.length) {
    d3.select(svgEl.parentElement)
      .append("p")
      .attr("class", "meta")
      .text("No flow links (nothing to draw).");
    return;
  }

  var panel = svgEl.parentElement;
  var w = Math.max(480, (panel && panel.clientWidth) || 640);
  var h = 400;

  var sankey = sankeyFactory()
    .nodeWidth(12)
    .nodePadding(6)
    .extent([
      [10, 10],
      [w - 10, h - 10],
    ]);

  var graph = sankey({
    nodes: nodes.map(function (d) {
      return Object.assign({}, d);
    }),
    links: links.map(function (d) {
      return {
        source: d.source,
        target: d.target,
        value: d.value,
      };
    }),
  });

  function nodeFill(d) {
    if (d.kind === "start") return "#6b7280";
    if (d.kind === "end") return d.stepSuccess ? "#15803d" : "#b32525";
    if (d.stepSuccess) return "#b32525";
    return "#0d8050";
  }

  var svg = d3.select(svgEl);
  svg.selectAll("*").remove();
  svg.attr("viewBox", [0, 0, w, h])
    .attr("width", w)
    .attr("height", h)
    .attr("role", "img")
    .attr("aria-label", "Aggregate attack path flow by stage");

  var g = svg.append("g").attr("class", "path-overview-sankey-layer");

  var linkPath = linkHorizontal();
  g.selectAll("path.path-overview-sankey-link")
    .data(graph.links)
    .join("path")
    .attr("class", "path-overview-sankey-link")
    .attr("d", linkPath)
    .attr("fill", "none")
    .attr("stroke", "#94a3b8")
    .attr("stroke-opacity", 0.35)
    .attr("stroke-width", function (d) {
      return Math.max(1, d.width || 1);
    })
    .sort(function (a, b) {
      return (b.width || 0) - (a.width || 0);
    });

  var nodeG = g
    .selectAll("g.path-overview-sankey-node")
    .data(graph.nodes)
    .join("g")
    .attr("class", "path-overview-sankey-node")
    .attr("transform", function (d) {
      return "translate(" + d.x0 + "," + d.y0 + ")";
    });

  nodeG
    .append("rect")
    .attr("height", function (d) {
      return Math.max(1, d.y1 - d.y0);
    })
    .attr("width", function (d) {
      return Math.max(1, d.x1 - d.x0);
    })
    .attr("fill", nodeFill)
    .attr("fill-opacity", 0.9)
    .attr("rx", 2)
    .attr("stroke", "#e5e7eb")
    .attr("stroke-width", 0.5)
    .each(function (d) {
      var t = (d.label || d.id || "").toString();
      d3.select(this).append("title").text(t);
    });

  nodeG
    .append("text")
    .attr("x", function (d) {
      return (d.x0 < w / 2 ? 6 : -6) + (d.x1 - d.x0);
    })
    .attr("y", function (d) {
      return (d.y1 - d.y0) / 2;
    })
    .attr("dy", "0.35em")
    .attr("text-anchor", function (d) {
      return d.x0 < w / 2 ? "start" : "end";
    })
    .attr("fill", "#374151")
    .style("font-size", "9px")
    .style("pointer-events", "none")
    .text(function (d) {
      var s = (d.label || "").toString();
      var maxC = 28;
      return s.length > maxC ? s.slice(0, maxC - 1) + "\u2026" : s;
    });
})();
