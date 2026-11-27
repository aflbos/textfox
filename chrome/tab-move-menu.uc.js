(() => {
  "use strict";

  const browser = window.gBrowser;
  const contextMenu = document.getElementById("tabContextMenu");
  const moveMenu = document.getElementById("context_moveTabOptions");
  if (!browser || !contextMenu || !moveMenu || document.getElementById("textfox-move-tab-back")) {
    return;
  }

  const tabs = browser.tabContainer;
  tabs.setAttribute("textfox-tree-disclosure", "");
  const { ShortcutUtils } = ChromeUtils.importESModule("resource://gre/modules/ShortcutUtils.sys.mjs");
  const { SessionStore } = ChromeUtils.importESModule("resource:///modules/sessionstore/SessionStore.sys.mjs");
  const portuguese = /^pt(?:-|$)/i.test(Services.locale.appLocaleAsBCP47);
  const treeColorKey = "textfox-tree-color";
  const palette = new Map([
    ["blue", portuguese ? "Azul" : "Blue"],
    ["cyan", portuguese ? "Ciano" : "Cyan"],
    ["green", portuguese ? "Verde" : "Green"],
    ["yellow", portuguese ? "Amarelo" : "Yellow"],
    ["orange", portuguese ? "Laranja" : "Orange"],
    ["pink", portuguese ? "Rosa" : "Pink"],
    ["purple", portuguese ? "Roxo" : "Purple"],
  ]);
  const labels = portuguese
    ? {
        vertical: ["Mover uma posição para cima", "Mover uma posição para baixo"],
        ordered: ["Mover uma posição para trás", "Mover uma posição para frente"],
      }
    : {
        vertical: ["Move One Position Up", "Move One Position Down"],
        ordered: ["Move One Position Back", "Move One Position Forward"],
      };

  // Waterfox's disclosure button only handles input with the sidebar expanded.
  function handleCollapsedDisclosure(event) {
    if (event.button !== 0 || tabs.hasAttribute("expanded") ||
        !window.TreeTabsDnD?._isEnabled?.(tabs)) return;
    const button = event.target?.closest(".tab-tree-disclosure:not([hidden])");
    const tab = button?.closest(".tabbrowser-tab[data-tree-has-children]");
    if (!tab || tab.closing || tab.pinned) return;

    event.preventDefault();
    event.stopPropagation();
    if (event.type === "click") browser.TreeTabsService.toggleCollapsed(tab);
  }

  for (const type of ["mousedown", "click", "dblclick"]) {
    tabs.addEventListener(type, handleCollapsedDisclosure, { capture: true });
  }

  let paintedTreeRows = new Set();
  let treeFrame = 0;

  function getSavedTreeColor(root) {
    const color = SessionStore.getCustomTabValue(root, treeColorKey);
    return palette.has(color) ? color : "";
  }

  function paintTreeLines() {
    treeFrame = 0;
    const expanded = tabs.hasAttribute("expanded");
    const tree = browser.TreeTabsService;
    const rows = !tabs.verticalMode || !tree
      ? []
      : tabs.visibleTabs.filter(tab => tab.hasAttribute("data-tree-level") &&
          !tab.hasAttribute("data-tree-hidden") && !tab.closing && !tab.pinned);
    const indices = new Map(rows.map((tab, index) => [tab, index]));
    // A restored, unloaded parent may not have a linkedPanel yet.
    const parents = rows.map(tab => tree.getParent(tab));
    const ancestry = rows.map(tab => {
      const ancestors = tree.getAncestors(tab);
      return { root: ancestors.at(-1) ?? tab, ancestors: new Set(ancestors) };
    });
    const colors = new Map();
    const lastChildren = new Map();
    const tracks = rows.map(() => []);
    const depth = tab => expanded
      ? Number(tab.style.getPropertyValue("--tree-level"))
      : Math.min(Number(tab.dataset.treeLevel), 2);
    const offset = level => `calc(var(--textfox-tree-track-start) + ${level} * var(--textfox-tree-track-step))`;
    const ink = "linear-gradient(currentColor 0 0)";
    for (const [index, tab] of parents.entries()) {
      const parent = indices.get(tab);
      if (parent !== undefined && parent < index) lastChildren.set(parent, index);
    }

    // Each branch starts at its parent's center and ends at the last visible child's center.
    for (const [parent, last] of lastChildren) {
      const level = depth(rows[parent]);
      tracks[parent][level] |= 2;
      for (let row = parent + 1; row < last; row++) {
        if (ancestry[row].ancestors.has(rows[parent])) tracks[row][level] |= 3;
      }
      tracks[last][level] |= 1;
    }

    const nextPainted = new Set();
    for (const [index, tab] of rows.entries()) {
      const lines = tracks[index].flatMap((track, level) => {
        if (!track) return [];
        const edge = track === 2 ? "bottom" : "top";
        const half = expanded ? "calc(50% + 0.5px)" : "50%";
        const height = track === 3 ? "100%" : half;
        return `${ink} var(--textfox-tree-side) ${offset(level)} ${edge} 0 / 1px ${height} no-repeat`;
      });
      const parent = parents[index];
      if (expanded && lines.length && (indices.has(parent) || lastChildren.has(index))) {
        const anchor = indices.has(parent) ? parent : tab;
        const start = offset(depth(anchor));
        const width = `max(0px, calc(var(--textfox-tree-frame-start) - ${start}))`;
        lines.push(`${ink} var(--textfox-tree-side) ${start} top 50% / ${width} 1px no-repeat`);
      }
      const { root } = ancestry[index];
      if (!colors.has(root)) {
        colors.set(root, root.hasAttribute("data-tree-has-children") ? getSavedTreeColor(root) : "");
      }
      const color = colors.get(root);
      if (!lines.length && !color && !paintedTreeRows.has(tab)) continue;
      tab.style.setProperty("--textfox-tree-lines", lines.join(", "));
      tab.toggleAttribute("textfox-tree-line", lines.length > 0);
      if (color) tab.setAttribute("textfox-tree-color", color);
      else tab.removeAttribute("textfox-tree-color");
      tab.toggleAttribute("textfox-tree-color-root", Boolean(color && tab === root));
      if (lines.length || color) nextPainted.add(tab);
    }
    for (const tab of paintedTreeRows) {
      if (nextPainted.has(tab)) continue;
      tab.style.removeProperty("--textfox-tree-lines");
      tab.removeAttribute("textfox-tree-line");
      tab.removeAttribute("textfox-tree-color");
      tab.removeAttribute("textfox-tree-color-root");
    }
    paintedTreeRows = nextPainted;
  }

  function scheduleTreePaint() {
    if (!treeFrame) treeFrame = window.requestAnimationFrame(paintTreeLines);
  }

  const treeObserver = new MutationObserver(scheduleTreePaint);
  treeObserver.observe(tabs, {
    subtree: true,
    childList: true,
    attributeFilter: ["expanded", "orient", "data-tree-level", "data-tree-parent", "data-tree-hidden", "data-tree-has-children",
      "hidden", "collapsed", "closing"],
  });
  tabs.addEventListener("SSTabRestoring", scheduleTreePaint);
  tabs.addEventListener("SSTabRestored", scheduleTreePaint);
  scheduleTreePaint();
  window.addUnloadListener?.(() => {
    treeObserver.disconnect();
    tabs.removeEventListener("SSTabRestoring", scheduleTreePaint);
    tabs.removeEventListener("SSTabRestored", scheduleTreePaint);
    window.cancelAnimationFrame(treeFrame);
  });

  function getMove(tab, direction) {
    if (!tab?.visible || tab.closing || tab.multiselected) return null;

    const tree = browser.TreeTabsService;
    const treeDrag = window.TreeTabsDnD;
    if (!tab.pinned && treeDrag?._isEnabled?.(tabs)) {
      if (typeof treeDrag._syncSubtreeStripPosition !== "function") return null;
      const node = treeDrag._getLogicalTab(tab);
      const parent = tree.getParent(node);
      const peers = parent ? tree.getChildren(parent) : tree.getRootTabs(window);
      const index = peers.indexOf(node);
      if (index < 0) return null;
      const neighbor = peers[index + direction];
      if (!neighbor?.visible || neighbor.closing || neighbor.pinned || neighbor.group !== node.group) {
        return null;
      }
      return () => {
        tree.moveTabSubtree(node, index + direction);
        treeDrag._syncSubtreeStripPosition(node);
      };
    }

    const element = tab.splitview || tab;
    const peers = [...new Set(tabs.visibleTabs.filter(other => other.pinned === tab.pinned)
      .map(other => other.splitview || other))];
    const index = peers.indexOf(element);
    const neighbor = index >= 0 ? peers[index + direction] : null;
    if (!neighbor || neighbor.parentNode !== element.parentNode || neighbor.closing) return null;
    return () => {
      if (direction < 0) browser.moveTabsBefore([element], neighbor);
      else browser.moveTabsAfter([element], neighbor);
    };
  }

  function getContextMove(direction) {
    const context = window.TabContextMenu;
    return context?.multiselected ? null : getMove(context?.contextTab, direction);
  }

  function getParentChoices() {
    const context = window.TabContextMenu;
    const tab = context?.contextTab;
    const drag = window.TreeTabsDnD;
    if (!tab?.visible || tab.closing || tab.pinned || context.multiselected ||
        !drag?._isEnabled?.(tabs) || typeof drag._syncSubtreeStripPosition !== "function") {
      return [];
    }

    const tree = browser.TreeTabsService;
    const child = drag._getLogicalTab(tab);
    const currentParent = tree.getParent(child);
    const descendants = new Set(tree.getDescendants(child));
    const state = tree._getStateForTab?.(child)?.state;
    return tabs.visibleTabs.filter(parent =>
      parent !== child && parent !== currentParent && drag._getLogicalTab(parent) === parent &&
      !parent.closing && !parent.pinned && parent.group === child.group && !descendants.has(parent) &&
      !(state && tree._wouldExceedMaxDepth?.(state, parent, child))
    );
  }

  const items = [-1, 1].map((direction, index) => {
    const backward = direction < 0;
    const item = document.createXULElement("menuitem");
    item.id = backward ? "textfox-move-tab-back" : "textfox-move-tab-forward";
    item.addEventListener("command", () => getContextMove(direction)?.());

    // The browser already dispatches Ctrl+Shift+Page Up/Down to these methods.
    const method = backward ? "moveTabBackward" : "moveTabForward";
    const nativeMove = browser[method];
    if (typeof nativeMove === "function") {
      const moveSelected = () => getMove(browser.selectedTab, direction)?.();
      browser[method] = moveSelected;
      window.addUnloadListener?.(() => {
        if (browser[method] === moveSelected) browser[method] = nativeMove;
      });

      const key = document.createXULElement("key");
      key.setAttribute("modifiers", "control,shift");
      key.setAttribute("keycode", backward ? "VK_PAGE_UP" : "VK_PAGE_DOWN");
      item.setAttribute("acceltext", ShortcutUtils.prettifyShortcut(key));
    }

    return { item, index, direction };
  });

  const attachMenu = document.createXULElement("menu");
  attachMenu.id = "textfox-attach-tab";
  attachMenu.hidden = true;
  attachMenu.setAttribute("label", portuguese ? "Tornar filha de" : "Make Child of");
  const attachPopup = document.createXULElement("menupopup");
  attachMenu.append(attachPopup);

  attachPopup.addEventListener("popupshowing", event => {
    if (event.target !== attachPopup) return;
    const child = window.TreeTabsDnD?._getLogicalTab(window.TabContextMenu?.contextTab);
    attachPopup.replaceChildren(...getParentChoices().map(parent => {
      const item = document.createXULElement("menuitem");
      const title = parent.label;
      item.setAttribute("label", title.length > 80 ? title.slice(0, 79) + "…" : title);
      item.setAttribute("tooltiptext", title);
      item.addEventListener("command", () => {
        const drag = window.TreeTabsDnD;
        if (drag?._getLogicalTab(window.TabContextMenu?.contextTab) !== child ||
            !getParentChoices().includes(parent)) return;
        if (browser.TreeTabsService.attachTab(child, parent)) drag._syncSubtreeStripPosition(child);
      });
      return item;
    }));
  });
  attachPopup.addEventListener("popuphidden", event => {
    if (event.target === attachPopup) attachPopup.replaceChildren();
  });

  function getContextTreeRoot() {
    const context = window.TabContextMenu;
    const tab = context?.contextTab;
    const drag = window.TreeTabsDnD;
    if (!tab?.visible || tab.closing || tab.pinned || context.multiselected ||
        !drag?._isEnabled?.(tabs)) return null;

    const tree = browser.TreeTabsService;
    const node = drag._getLogicalTab(tab);
    const root = tree.getAncestors(node).at(-1) ?? node;
    return tree.getChildren(root).length ? root : null;
  }

  const colorMenu = document.createXULElement("menu");
  colorMenu.id = "textfox-tree-color-menu";
  colorMenu.hidden = true;
  colorMenu.setAttribute("label", portuguese ? "Cor da árvore" : "Tree Color");
  const colorPopup = document.createXULElement("menupopup");
  colorMenu.append(colorPopup);

  const colorItems = [...palette, ["", portuguese ? "Voltar ao padrão" : "Use Default"]]
    .map(([color, label]) => {
      const item = document.createXULElement("menuitem");
      item.setAttribute("type", "radio");
      item.setAttribute("name", "textfox-tree-color");
      item.setAttribute("label", label);
      item.setAttribute("value", color);
      if (color) item.setAttribute("textfox-tree-color", color);
      item.addEventListener("command", () => {
        const root = getContextTreeRoot();
        if (!root) return;
        if (color) SessionStore.setCustomTabValue(root, treeColorKey, color);
        else SessionStore.deleteCustomTabValue(root, treeColorKey);
        scheduleTreePaint();
      });
      colorPopup.append(item);
      return item;
    });
  colorPopup.addEventListener("popupshowing", event => {
    if (event.target !== colorPopup) return;
    const root = getContextTreeRoot();
    const color = root ? getSavedTreeColor(root) : "";
    for (const item of colorItems) item.checked = item.getAttribute("value") === color;
  });
  const firstSeparator = document.createXULElement("menuseparator");
  const lastSeparator = document.createXULElement("menuseparator");
  const section = [firstSeparator, ...items.map(({ item }) => item), attachMenu, colorMenu, lastSeparator];
  for (const entry of section) entry.hidden = true;
  moveMenu.after(...section);

  contextMenu.addEventListener("popupshowing", event => {
    if (event.target !== contextMenu) return;
    const context = window.TabContextMenu;
    const tab = context?.contextTab;
    const available = Boolean(tab?.visible && !tab.closing && !context.multiselected);
    firstSeparator.hidden = lastSeparator.hidden = !available;
    const grid = tab?.pinned && tabs.isContainerVerticalPinnedGrid?.(tab);
    const wording = tabs.verticalMode && !grid ? labels.vertical : labels.ordered;
    for (const { item, index, direction } of items) {
      item.hidden = !available;
      item.setAttribute("label", wording[index]);
      item.disabled = !getContextMove(direction);
    }
    attachMenu.hidden = !available || !window.TreeTabsDnD?._isEnabled?.(tabs);
    attachMenu.disabled = !getParentChoices().length;
    colorMenu.hidden = !available || !getContextTreeRoot();
  });
})();
