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
    tabs.removeAttribute("textfox-drop-between");
  }

  const dragAndDrop = tabs.tabDragAndDrop;
  const updateTabStyles = dragAndDrop?._updateTabStylesOnDrag;
  const treeDnD = window.TreeTabsDnD;
  const nativeAttachTarget = treeDnD?.getAttachTarget;
  const centeredDrags = new WeakSet();

  function getAttachTarget(container, event, dragged, ...args) {
    const target = nativeAttachTarget.call(this, container, event, dragged, ...args);
    if (!target || container !== tabs || dragged.container !== tabs ||
        dragged._dragData?.fromTabList || dragAndDrop?.getDropEffectForTabDrag(event) !== "move") {
      return target;
    }

    // Use the same unanimated bounds as Waterfox for dragover and drop.
    const row = this._getRowBounds(target);
    const inset = row.height / 3;
    return event.clientY >= row.top + inset && event.clientY <= row.bottom - inset
      ? target
      : null;
  }

  if (typeof nativeAttachTarget === "function" && typeof treeDnD._getRowBounds === "function") {
    treeDnD.getAttachTarget = getAttachTarget;
  }

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

  function getPinnedSlot(data, target, item, rtl) {
    const index = data.animDropElementIndex;
    const columns = dragAndDrop?._maxTabsPerRow;
    const reference = target.currentIndex ?? target.elementIndex;
    if (!Number.isInteger(index) || !Number.isInteger(reference) || !columns) return null;

    // The native index counts the moved tabs. The new slot does not.
    const slot = index - data.movingTabs.filter(tab => tab.elementIndex < index).length;
    const column = slot % columns;
    const columnDelta = column - reference % columns;
    const rowDelta = Math.floor(slot / columns) - Math.floor(reference / columns);
    const transform = new DOMMatrixReadOnly(getComputedStyle(target).transform);
    const left = item.left - transform.m41 + columnDelta * item.width * (rtl ? -1 : 1);
    const top = item.top - transform.m42 + rowDelta * item.height;
    return {
      rect: new DOMRect(left, top, item.width, item.height),
      rowBreak: slot > 0 && column === 0,
    };
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

    const grid = tabs.isContainerVerticalPinnedGrid?.(dragged);
    const rtl = getComputedStyle(tabs).direction === "rtl";
    const slot = grid ? getPinnedSlot(data, target, item, rtl) : null;
    const vertical = tabs.verticalMode && (!grid || slot?.rowBreak);
    const viewport = (dragged.pinned
      ? tabs.pinnedTabsContainer?.getBoundingClientRect()
      : tabs.arrowScrollbox?.scrollClientRect) ?? tabs.getBoundingClientRect();
    const destination = slot?.rect ?? item;
    const before = Boolean(slot) || data.dropBefore;
    const drawBefore = vertical ? before : before !== rtl;
    const targetEdge = vertical
      ? (drawBefore ? destination.top : destination.bottom)
      : (drawBefore ? destination.left : destination.right);
    const span = slot?.rowBreak ? viewport : destination;
    const start = vertical ? Math.max(span.left, viewport.left) : Math.max(span.top, viewport.top);
    const end = vertical ? Math.min(span.right, viewport.right) : Math.min(span.bottom, viewport.bottom);
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
    const visible = showPosition(dragged);
    indicator.hidden = !visible;
    tabs.toggleAttribute("textfox-drop-between", visible);
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
    if (treeDnD?.getAttachTarget?.(tabs, event, dragged)) {
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
    if (treeDnD?.getAttachTarget === getAttachTarget) {
      treeDnD.getAttachTarget = nativeAttachTarget;
    }
  });
})();
