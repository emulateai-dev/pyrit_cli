/**
 * Tangled tree layout (attack paths) after Observable "tangled-tree-visualization-ii".
 * Original: Matteo Abrate (IIT CNR), MIT License.
 * Port: Takanori Fujiwara d3-gallery-javascript, BSD-3-Clause.
 * Embedded for pyrit-cli benchmark HTML reports.
 */
(function () {
  var jsonEl = document.getElementById("bench-attack-paths-json");
  var svgEl = document.getElementById("paths-tree-svg");
  if (!jsonEl || !svgEl || typeof d3 === "undefined") return;

  var treeData;
  try {
    treeData = JSON.parse(jsonEl.textContent);
  } catch (e) {
    return;
  }
  if (!treeData || (treeData.children == null && treeData.name == null)) {
    d3.select(svgEl.parentElement)
      .append("p")
      .attr("class", "meta")
      .text("No attack path data for this run.");
    return;
  }

  var nextId = 0;
  function genId() {
    return "n" + nextId++;
  }

  function compactLabel(node) {
    var t = node.type;
    var n = (node.name || "").toString();
    if (t === "dataset") return n.length > 24 ? n.slice(0, 23) + "\u2026" : n;
    if (t === "prompt") {
      var m = n.match(/^#(\d+)\b/);
      if (m) return "#" + m[1];
      return n.length > 12 ? n.slice(0, 11) + "\u2026" : n;
    }
    if (t === "step") {
      if (node.stage === "baseline") return "bl";
      if (node.stage === "baseline_converter") return "bl+";
      if (node.stage === "tap") return "TAP";
      if (node.stage === "template_converter") {
        var tc = n.split("/").pop() || n;
        tc = tc.length > 10 ? "\u2026" + tc.slice(-9) : tc;
        return "t+" + tc;
      }
      if (node.stage === "template") {
        var tail = n.split("/").pop() || n;
        tail = tail.replace(/^template:/, "");
        tail = tail.length > 12 ? "\u2026" + tail.slice(-11) : tail;
        return "t\u00b7" + tail;
      }
      return n.length > 14 ? n.slice(0, 13) + "\u2026" : n;
    }
    return n.length > 16 ? n.slice(0, 15) + "\u2026" : n;
  }

  function fullTitle(node) {
    var n = (node.name || "").toString();
    var x = "";
    if (node.type === "prompt" && typeof node.final_success === "boolean")
      x = " \u2014 final " + (node.final_success ? "PASS" : "FAIL");
    if (node.type === "step")
      x =
        " (" +
        (node.stage || "") +
        ") \u2014 " +
        (node.success ? "jailbreak signal" : "defense held");
    return n + x;
  }

  function treeToLevels(data) {
    var levels = [];
    function walk(node, depth, parentId) {
      if (!levels[depth]) levels[depth] = [];
      var id = genId();
      var parents = parentId ? [parentId] : [];
      levels[depth].push({
        id: id,
        parents: parents,
        label: compactLabel(node),
        fullTitle: fullTitle(node),
        nodeType: node.type,
        stepSuccess: node.success,
      });
      var ch = node.children || [];
      for (var i = 0; i < ch.length; i++) walk(ch[i], depth + 1, id);
    }
    walk(data, 0, null);
    return levels;
  }

  function constructTangleLayout(levels, options) {
    options = options || {};
    var nodeWidth = options.nodeWidth != null ? options.nodeWidth : 76;
    var nodeHeight = options.nodeHeight != null ? options.nodeHeight : 18;
    var padding = options.padding != null ? options.padding : 8;
    var bundleWidth = options.bundleWidth != null ? options.bundleWidth : 10;
    var levelYPadding = options.levelYPadding != null ? options.levelYPadding : 0;
    var metroD = options.metroD != null ? options.metroD : 3;
    var minFamilyHeight = options.minFamilyHeight != null ? options.minFamilyHeight : 8;
    var c = options.c != null ? options.c : 12;
    var bigc = nodeWidth + c;

    levels.forEach(function (l, i) {
      l.forEach(function (n) {
        n.level = i;
      });
    });

    var nodes = levels.reduce(function (a, x) {
      return a.concat(x);
    }, []);
    var nodesIndex = {};
    for (var ni = 0; ni < nodes.length; ni++) nodesIndex[nodes[ni].id] = nodes[ni];

    for (var nj = 0; nj < nodes.length; nj++) {
      var node = nodes[nj];
      node.parents = (node.parents === undefined ? [] : node.parents).map(function (p) {
        return nodesIndex[p];
      });
    }

    for (var li = 0; li < levels.length; li++) {
      var level = levels[li];
      var index = {};
      level.forEach(function (n) {
        if (n.parents.length === 0) return;
        var bid = n.parents
          .map(function (d) {
            return d.id;
          })
          .sort()
          .join("-X-");
        if (index[bid]) {
          index[bid].parents = index[bid].parents.concat(n.parents);
        } else {
          index[bid] = {
            id: bid,
            parents: n.parents.slice(),
            level: li,
            span: li - d3.min(n.parents, function (p) {
              return p.level;
            }),
          };
        }
        n.bundle = index[bid];
      });
      level.bundles = Object.keys(index).map(function (key) {
        return index[key];
      });
      for (var bi = 0; bi < level.bundles.length; bi++) level.bundles[bi].i = bi;
    }

    var links = [];
    for (var nk = 0; nk < nodes.length; nk++) {
      var nd = nodes[nk];
      for (var pi = 0; pi < nd.parents.length; pi++) {
        links.push({
          source: nd,
          bundle: nd.bundle,
          target: nd.parents[pi],
        });
      }
    }

    var bundles = levels.reduce(function (a, x) {
      return a.concat(x.bundles || []);
    }, []);

    for (var bx = 0; bx < bundles.length; bx++) {
      var bundle = bundles[bx];
      for (var pj = 0; pj < bundle.parents.length; pj++) {
        var parent = bundle.parents[pj];
        if (parent.bundlesIndex === undefined) parent.bundlesIndex = {};
        if (!(bundle.id in parent.bundlesIndex)) parent.bundlesIndex[bundle.id] = [];
        parent.bundlesIndex[bundle.id].push(bundle);
      }
    }

    for (var nl = 0; nl < nodes.length; nl++) {
      var nn = nodes[nl];
      if (nn.bundlesIndex !== undefined) {
        nn.bundles = Object.keys(nn.bundlesIndex).map(function (key) {
          return nn.bundlesIndex[key];
        });
      } else {
        nn.bundlesIndex = {};
        nn.bundles = [];
      }
      nn.bundles.sort(function (a, b) {
        return d3.descending(
          d3.max(a, function (d) {
            return d.span;
          }),
          d3.max(b, function (d) {
            return d.span;
          })
        );
      });
      for (var bj = 0; bj < nn.bundles.length; bj++) nn.bundles[bj].i = bj;
    }

    for (var lk = 0; lk < links.length; lk++) {
      var link = links[lk];
      if (link.bundle.links === undefined) link.bundle.links = [];
      link.bundle.links.push(link);
    }

    for (var nm = 0; nm < nodes.length; nm++) {
      nodes[nm].height = (Math.max(1, nodes[nm].bundles.length) - 1) * metroD;
    }

    var xOffset = padding;
    var yOffset = padding;
    for (var lj = 0; lj < levels.length; lj++) {
      var lvl = levels[lj];
      xOffset += lvl.bundles.length * bundleWidth;
      yOffset += levelYPadding;
      for (var vn = 0; vn < lvl.length; vn++) {
        var vnNode = lvl[vn];
        vnNode.x = vnNode.level * nodeWidth + xOffset;
        vnNode.y = nodeHeight + yOffset + vnNode.height / 2;
        yOffset += nodeHeight + vnNode.height;
      }
    }

    var totalLength = 0;
    for (var lk2 = 0; lk2 < levels.length; lk2++) {
      var lvl2 = levels[lk2];
      lvl2.bundles.forEach(function (bundle2) {
        bundle2.x =
          d3.max(bundle2.parents, function (d) {
            return d.x;
          }) +
          nodeWidth +
          (lvl2.bundles.length - 1 - bundle2.i) * bundleWidth;
        bundle2.y = totalLength * nodeHeight;
      });
      totalLength += lvl2.length;
    }

    for (var lk3 = 0; lk3 < links.length; lk3++) {
      var Lk = links[lk3];
      Lk.xt = Lk.target.x;
      Lk.yt =
        Lk.target.y +
        Lk.target.bundlesIndex[Lk.bundle.id].i * metroD -
        (Lk.target.bundles.length * metroD) / 2 +
        metroD / 2;
      Lk.xb = Lk.bundle.x;
      Lk.yb = Lk.bundle.y;
      Lk.xs = Lk.source.x;
      Lk.ys = Lk.source.y;
    }

    var yNegativeOffset = 0;
    for (var lc = 0; lc < levels.length; lc++) {
      var lvlc = levels[lc];
      if (lvlc.bundles.length > 0) {
        var bmin = d3.min(lvlc.bundles, function (bundle3) {
          return d3.min(bundle3.links, function (link2) {
            return link2.ys - 2 * c - (link2.yt + c);
          });
        });
        yNegativeOffset += -minFamilyHeight + (bmin != null ? bmin : 0);
      }
      for (var vc = 0; vc < lvlc.length; vc++) lvlc[vc].y -= yNegativeOffset;
    }

    for (var lk4 = 0; lk4 < links.length; lk4++) {
      var L2 = links[lk4];
      L2.yt =
        L2.target.y +
        L2.target.bundlesIndex[L2.bundle.id].i * metroD -
        (L2.target.bundles.length * metroD) / 2 +
        metroD / 2;
      L2.ys = L2.source.y;
      L2.c1 =
        L2.source.level - L2.target.level > 1
          ? Math.min(bigc, L2.xb - L2.xt, L2.yb - L2.yt) - c
          : c;
      L2.c2 = c;
    }

    var layout = {
      width: d3.max(nodes, function (node) {
        return node.x;
      }) +
        nodeWidth +
        2 * padding,
      height:
        d3.max(nodes, function (node2) {
          return node2.y;
        }) +
        nodeHeight / 2 +
        2 * padding,
      nodeHeight: nodeHeight,
      nodeWidth: nodeWidth,
    };

    return {
      nodes: nodes,
      links: links,
      bundles: bundles,
      layout: layout,
    };
  }

  function linkPathSegment(l) {
    return (
      "M" +
      l.xt +
      " " +
      l.yt +
      "L" +
      (l.xb - l.c1) +
      " " +
      l.yt +
      "A" +
      l.c1 +
      " " +
      l.c1 +
      " 90 0 1 " +
      l.xb +
      " " +
      (l.yt + l.c1) +
      "L" +
      l.xb +
      " " +
      (l.ys - l.c2) +
      "A" +
      l.c2 +
      " " +
      l.c2 +
      " 90 0 0 " +
      (l.xb + l.c2) +
      " " +
      l.ys +
      "L" +
      l.xs +
      " " +
      l.ys
    );
  }

  function nodeFill(n) {
    var t = n.nodeType;
    if (t === "dataset") return "#6b7280";
    if (t === "prompt") return "#3d5dcc";
    if (t === "step") return n.stepSuccess ? "#b32525" : "#0d8050";
    return "#9ca3af";
  }

  var levels = treeToLevels(treeData);
  var T = constructTangleLayout(levels, {
    nodeWidth: 72,
    nodeHeight: 17,
    bundleWidth: 9,
    metroD: 3,
    padding: 10,
    c: 11,
    minFamilyHeight: 6,
  });

  var W = T.layout.width;
  var H = T.layout.height;
  var nh = T.layout.nodeHeight;
  var nw = T.layout.nodeWidth;

  var svg = d3.select(svgEl);
  svg.selectAll("*").remove();
  svg.attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H);

  var g = svg.append("g").attr("class", "paths-tangle-root");

  g.selectAll("path.paths-tangle-bundle")
    .data(T.bundles)
    .join("path")
    .attr("class", "paths-tangle-bundle")
    .attr("fill", "none")
    .attr("stroke", "#94a3b8")
    .attr("stroke-width", 1.1)
    .attr("d", function (b) {
      return b.links.map(linkPathSegment).join("");
    });

  var nodeG = g
    .selectAll("g.paths-tangle-node")
    .data(T.nodes)
    .join("g")
    .attr("class", "paths-tangle-node")
    .attr("transform", function (d) {
      return "translate(" + d.x + "," + (d.y - nh / 2) + ")";
    });

  nodeG
    .append("rect")
    .attr("width", nw)
    .attr("height", nh)
    .attr("rx", 3)
    .attr("fill", nodeFill)
    .attr("fill-opacity", 0.92)
    .attr("stroke", "#dfe3e8")
    .attr("stroke-width", 1)
    .each(function (d) {
      d3.select(this).append("title").text(d.fullTitle);
    });

  nodeG
    .append("text")
    .attr("x", 5)
    .attr("y", nh / 2)
    .attr("dy", "0.35em")
    .attr("fill", "#fff")
    .style("font-size", "9px")
    .style("pointer-events", "none")
    .text(function (d) {
      var s = d.label || "";
      var maxC = Math.max(8, Math.floor(nw / 5.5));
      return s.length > maxC ? s.slice(0, maxC - 1) + "\u2026" : s;
    });
})();
