(() => {
  "use strict";

  const tabs = window.gBrowser?.tabContainer;
  if (!tabs || document.getElementById("textfox-tab-drop-position")) {
    return;
  }

  const indicator = document.createElementNS("http://www.w3.org/1999/xhtml", "div");
  indicator.id = "textfox-tab-drop-position";
  indicator.setAttribute("aria-hidden", "true");
  indicator.hidden = true;
  document.body.append(indicator);

  const controller = new AbortController();
  const { signal } = controller;
  const tabType = "application/x-moz-tabbrowser-tab";
  let update = 0;

  function hide() {
    window.cancelAnimationFrame(update);
    indicator.hidden = true;
  }

  const dragAndDrop = tabs.tabDragAndDrop;
  const updateTabStyles = dragAndDrop?._updateTabStylesOnDrag;
  const centeredDrags = new WeakSet();

  function centerDraggedTab(dragged, dropEffect) {
    const result = updateTabStyles.call(this, dragged, dropEffect);
    const data = dragged._dragData;
    if (dropEffect === "move" && dragged.classList.contains("tabbrowser-tab") &&
        dragged.hasAttribute("dragtarget") && data && !centeredDrags.has(data)) {
      // Gecko positions the dragged tab absolutely before translating it.
      // Read its center after that layout change and keep detachment offsets.
      const rect = dragged.getBoundingClientRect();
      data.screenX = dragged.screenX + rect.width / 2;
      data.screenY = dragged.screenY + rect.height / 2;
      centeredDrags.add(data);
    }
    return result;
  }

  if (typeof updateTabStyles === "function") {
    dragAndDrop._updateTabStylesOnDrag = centerDraggedTab;
  }

  function maskBehindDraggedTab(dragged, vertical, edge, start, end) {
    const frame = dragged.querySelector(":scope > .tab-stack > .tab-background") ?? dragged;
    const bounds = frame.getBoundingClientRect();
    const nearEdge = vertical ? bounds.top : bounds.left;
    const farEdge = vertical ? bounds.bottom : bounds.right;
    const coverStart = Math.max(start, vertical ? bounds.left : bounds.top);
    const coverEnd = Math.min(end, vertical ? bounds.right : bounds.bottom);
    if (edge + 1.5 <= nearEdge || edge - 1.5 >= farEdge || coverEnd <= coverStart) {
      return "none";
    }

    // The native tab may be in a different stacking context. Cut the line
    // out behind its painted frame so it remains visible in the gutters.
    const from = `${coverStart - start}px`;
    const to = `${coverEnd - start}px`;
    const direction = vertical ? "to right" : "to bottom";
    return `linear-gradient(${direction}, currentColor ${from}, transparent ${from} ${to}, currentColor ${to})`;
  }

  function showPosition(dragged) {
    const data = dragged._dragData;
    const target = data?.dropElement;
    if (!target?.isConnected || typeof data.dropBefore !== "boolean") {
      return false;
    }

    const item = target.getBoundingClientRect();
    if (!item.width || !item.height) {
      return false;
    }

    const vertical = tabs.verticalMode && !tabs.isContainerVerticalPinnedGrid?.(dragged);
    const rtl = getComputedStyle(tabs).direction === "rtl";
    const viewport = (dragged.pinned
      ? tabs.pinnedTabsContainer?.getBoundingClientRect()
      : tabs.arrowScrollbox?.scrollClientRect) ?? tabs.getBoundingClientRect();
    const drawBefore = vertical ? data.dropBefore : data.dropBefore !== rtl;
    const targetEdge = vertical
      ? (drawBefore ? item.top : item.bottom)
      : (drawBefore ? item.left : item.right);
    const start = vertical ? Math.max(item.left, viewport.left) : Math.max(item.top, viewport.top);
    const end = vertical ? Math.min(item.right, viewport.right) : Math.min(item.bottom, viewport.bottom);
    const axisStart = vertical ? viewport.top : viewport.left;
    const axisEnd = vertical ? viewport.bottom : viewport.right;
    if (end <= start) {
      return false;
    }

    const edge = Math.max(axisStart, Math.min(targetEdge, axisEnd));
    indicator.dataset.axis = vertical ? "vertical" : "horizontal";
    indicator.style.left = `${vertical ? start : edge}px`;
    indicator.style.top = `${vertical ? edge : start}px`;
    indicator.style.setProperty("--textfox-drop-span", `${end - start}px`);
    indicator.style.maskImage = maskBehindDraggedTab(dragged, vertical, edge, start, end);
    return true;
  }

  function followPosition(dragged) {
    if (!tabs.hasAttribute("movingtab")) {
      hide();
      return;
    }
    indicator.hidden = !showPosition(dragged);
    update = window.requestAnimationFrame(() => followPosition(dragged));
  }

  tabs.addEventListener("dragover", event => {
    // Use the index computed by the browser after its own dragover handler,
    // and keep the native indicator for copies, links and cross-window drops.
    hide();
    const transfer = event.dataTransfer;
    const dragged = transfer?.mozItemCount ? transfer.mozGetDataAt(tabType, 0) : null;
    if (!event.defaultPrevented || dragged?.ownerDocument !== document ||
        !tabs.tabDragAndDrop?._tabDropIndicator?.hidden || dragged._dragData?.fromTabList) {
      return;
    }
    // Waterfox already highlights the parent for a drop that creates a child.
    if (window.TreeTabsDnD?.getAttachTarget?.(tabs, event, dragged)) {
      return;
    }
    update = window.requestAnimationFrame(() => followPosition(dragged));
  }, { signal });

  tabs.addEventListener("dragleave", event => {
    if (!tabs.contains(event.relatedTarget)) {
      hide();
    }
  }, { signal });
  window.addEventListener("dragend", hide, { capture: true, signal });
  window.addEventListener("drop", hide, { capture: true, signal });
  window.addEventListener("blur", hide, { signal });
  window.addUnloadListener?.(() => {
    hide();
    controller.abort();
    indicator.remove();
    if (dragAndDrop?._updateTabStylesOnDrag === centerDraggedTab) {
      dragAndDrop._updateTabStylesOnDrag = updateTabStyles;
    }
  });
})();
