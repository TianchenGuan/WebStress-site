"""
Occlusion Detection for LLMOS.
Computes element visibility based on z-index and bounds overlap.
"""

import copy
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Rect:
    """Rectangle representation for bounds calculations."""
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_bounds(cls, bounds: dict) -> Optional["Rect"]:
        """Create Rect from bounds dict. Returns None if bounds is invalid."""
        if not isinstance(bounds, dict):
            return None
        try:
            return cls(
                x=float(bounds.get("x", 0)),
                y=float(bounds.get("y", 0)),
                width=float(bounds.get("width", 0)),
                height=float(bounds.get("height", 0)),
            )
        except (TypeError, ValueError):
            return None

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0, self.width) * max(0, self.height)

    def intersects(self, other: "Rect") -> bool:
        """Check if two rectangles overlap."""
        if self.width <= 0 or self.height <= 0:
            return False
        if other.width <= 0 or other.height <= 0:
            return False
        return not (
            self.right <= other.x or
            other.right <= self.x or
            self.bottom <= other.y or
            other.bottom <= self.y
        )

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        """Get the intersection rectangle. Returns None if no intersection."""
        if not self.intersects(other):
            return None

        x = max(self.x, other.x)
        y = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)

        return Rect(x=x, y=y, width=right - x, height=bottom - y)

    def contains(self, other: "Rect") -> bool:
        """Check if this rectangle fully contains another."""
        return (
            self.x <= other.x and
            self.y <= other.y and
            self.right >= other.right and
            self.bottom >= other.bottom
        )

    def to_dict(self) -> dict:
        """Convert to bounds dict."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class OcclusionInfo:
    """Information about an element's occlusion state."""
    bid: str
    is_fully_occluded: bool
    is_partially_occluded: bool
    visible_area_percent: float  # 0.0 to 100.0
    occluded_by: list[str]  # List of bids that occlude this element
    invisible_regions: list[dict]  # List of bounds dicts for occluded areas


def get_z_index(node: dict) -> int:
    """Get the z_index of a node, defaulting to 0."""
    return node.get("z_index", 0)


def collect_nodes_with_bounds(
    node: dict,
    parent_z_index: int = 0,
    sibling_index: int = 0,
    ancestors: tuple = (),
) -> list[tuple[dict, Rect, float, tuple]]:
    """
    Recursively collect all nodes with their bounds and effective z_index.

    The effective z_index is computed as:
    - Explicit z_index if present
    - Otherwise, parent's z_index + small increment based on sibling order

    This ensures children of high z_index parents are also high z_index,
    and later siblings appear on top of earlier siblings.

    Args:
        node: The UI tree node.
        parent_z_index: The parent's effective z_index.
        sibling_index: This node's index among siblings (for tie-breaking).
        ancestors: Tuple of ancestor bids (for filtering parent-child occlusion).

    Returns:
        List of (node, Rect, effective_z_index, ancestors) tuples.
    """
    results = []

    if not isinstance(node, dict):
        return results

    # Get bounds
    bounds = node.get("bounds")
    rect = Rect.from_bounds(bounds) if bounds else None

    # Compute effective z_index
    # Explicit z_index overrides, otherwise inherit from parent with sibling offset
    explicit_z = node.get("z_index")
    if explicit_z is not None:
        effective_z = explicit_z
    else:
        # Use parent z_index + fractional offset based on sibling order
        # Multiply sibling_index by 0.001 to ensure later siblings are on top
        # but the difference is small enough to not affect explicit z_index ordering
        effective_z = parent_z_index + sibling_index * 0.001

    bid = node.get("bid")

    # Only include nodes that have bounds
    if rect is not None and rect.area > 0:
        results.append((node, rect, effective_z, ancestors))

    # Recurse into children with updated ancestors
    new_ancestors = ancestors + (bid,) if bid else ancestors
    children = node.get("children", [])
    if isinstance(children, list):
        for i, child in enumerate(children):
            results.extend(collect_nodes_with_bounds(child, effective_z, i, new_ancestors))

    return results


def compute_occlusion(ui_tree: dict) -> dict[str, OcclusionInfo]:
    """
    Compute occlusion information for all elements in the UI tree.

    Note: This is a simpler/faster version that may overcount overlapping occluders.
    Use compute_occlusion_precise() for accurate area calculations.

    Args:
        ui_tree: The root UI tree node.

    Returns:
        Dict mapping bid to OcclusionInfo.
    """
    # Collect all nodes with bounds
    nodes = collect_nodes_with_bounds(ui_tree)

    # Sort by z_index (lower first, so we process bottom elements first)
    nodes_sorted = sorted(nodes, key=lambda x: x[2])

    occlusion_map: dict[str, OcclusionInfo] = {}

    for i, (node, rect, z_index, ancestors) in enumerate(nodes_sorted):
        bid = node.get("bid")
        if bid is None:
            continue

        # Find all nodes with higher z_index that overlap this node
        occluders = []
        occluded_regions = []

        for other_node, other_rect, other_z_index, other_ancestors in nodes_sorted[i + 1:]:
            if other_z_index <= z_index:
                continue  # Not above us

            other_bid = other_node.get("bid")
            if other_bid is None:
                continue

            # Skip parent-child relationships
            if bid in other_ancestors or other_bid in ancestors:
                continue

            # Check if the other node occludes this one
            intersection = rect.intersection(other_rect)
            if intersection is not None and intersection.area > 0:
                occluders.append(other_bid)
                occluded_regions.append(intersection.to_dict())

        # Compute visible area
        # This is an approximation - we compute the union of occluded regions
        # For simplicity, we'll use the total occluded area (may overcount overlaps)
        total_occluded_area = sum(
            Rect.from_bounds(r).area for r in occluded_regions
            if Rect.from_bounds(r) is not None
        )

        original_area = rect.area
        # Clamp to original area (overlapping occluders may sum > original)
        occluded_area = min(total_occluded_area, original_area)
        visible_area = original_area - occluded_area
        visible_percent = (visible_area / original_area * 100) if original_area > 0 else 100.0

        is_fully_occluded = visible_percent <= 0
        is_partially_occluded = 0 < visible_percent < 100

        occlusion_map[bid] = OcclusionInfo(
            bid=bid,
            is_fully_occluded=is_fully_occluded,
            is_partially_occluded=is_partially_occluded,
            visible_area_percent=visible_percent,
            occluded_by=occluders,
            invisible_regions=occluded_regions,
        )

    return occlusion_map


def compute_occlusion_precise(ui_tree: dict) -> dict[str, OcclusionInfo]:
    """
    Compute occlusion with more precise area calculation.

    Uses a region-based approach to handle overlapping occluders correctly.
    This avoids overcounting when multiple occluders overlap each other.

    Important: Parent-child relationships are not considered occlusion.
    A parent is not occluded by its children, and a child is not occluded
    by its parent. Only sibling elements or elements from different branches
    can occlude each other.

    Args:
        ui_tree: The root UI tree node.

    Returns:
        Dict mapping bid to OcclusionInfo.
    """
    nodes = collect_nodes_with_bounds(ui_tree)
    nodes_sorted = sorted(nodes, key=lambda x: x[2])

    occlusion_map: dict[str, OcclusionInfo] = {}

    for i, (node, rect, z_index, ancestors) in enumerate(nodes_sorted):
        bid = node.get("bid")
        if bid is None:
            continue

        # Collect occluding rectangles
        occluders = []
        occluding_rects = []

        for other_node, other_rect, other_z_index, other_ancestors in nodes_sorted[i + 1:]:
            if other_z_index <= z_index:
                continue

            other_bid = other_node.get("bid")
            if other_bid is None:
                continue

            # Skip if other is a descendant of this node (child cannot occlude parent)
            if bid in other_ancestors:
                continue

            # Skip if this node is a descendant of other (parent cannot occlude child)
            if other_bid in ancestors:
                continue

            intersection = rect.intersection(other_rect)
            if intersection is not None and intersection.area > 0:
                occluders.append(other_bid)
                occluding_rects.append(intersection)

        # Compute union area of occluding rectangles using inclusion-exclusion
        # For simplicity with many occluders, we use a grid-based approach
        union_area = _compute_union_area(occluding_rects, rect)

        original_area = rect.area
        visible_area = original_area - union_area
        visible_percent = (visible_area / original_area * 100) if original_area > 0 else 100.0
        visible_percent = max(0, min(100, visible_percent))  # Clamp

        is_fully_occluded = visible_percent <= 0
        is_partially_occluded = 0 < visible_percent < 100

        # Convert occluding rects to dicts for invisible_regions
        invisible_regions = [r.to_dict() for r in occluding_rects]

        occlusion_map[bid] = OcclusionInfo(
            bid=bid,
            is_fully_occluded=is_fully_occluded,
            is_partially_occluded=is_partially_occluded,
            visible_area_percent=visible_percent,
            occluded_by=occluders,
            invisible_regions=invisible_regions,
        )

    return occlusion_map


def _compute_union_area(rects: list[Rect], bounding_rect: Rect) -> float:
    """
    Compute the union area of multiple rectangles within a bounding rect.

    Uses a sweep line algorithm for efficiency.
    """
    if not rects:
        return 0.0

    # Clip all rects to the bounding rect
    clipped = []
    for r in rects:
        intersection = bounding_rect.intersection(r)
        if intersection is not None and intersection.area > 0:
            clipped.append(intersection)

    if not clipped:
        return 0.0

    # Collect all x-coordinates for sweep
    x_coords = set()
    for r in clipped:
        x_coords.add(r.x)
        x_coords.add(r.right)
    x_sorted = sorted(x_coords)

    total_area = 0.0

    for i in range(len(x_sorted) - 1):
        x1 = x_sorted[i]
        x2 = x_sorted[i + 1]
        slice_width = x2 - x1

        if slice_width <= 0:
            continue

        # Find all rects that span this x-slice
        y_intervals = []
        for r in clipped:
            if r.x <= x1 and r.right >= x2:
                y_intervals.append((r.y, r.bottom))

        # Merge y intervals
        merged_height = _merge_intervals_length(y_intervals)
        total_area += slice_width * merged_height

    return total_area


def _merge_intervals_length(intervals: list[tuple[float, float]]) -> float:
    """Compute total length covered by merged intervals."""
    if not intervals:
        return 0.0

    sorted_intervals = sorted(intervals)
    merged_length = 0.0
    current_start, current_end = sorted_intervals[0]

    for start, end in sorted_intervals[1:]:
        if start <= current_end:
            # Overlapping, extend current interval
            current_end = max(current_end, end)
        else:
            # Non-overlapping, add current and start new
            merged_length += current_end - current_start
            current_start, current_end = start, end

    # Add final interval
    merged_length += current_end - current_start

    return merged_length


def filter_occluded_nodes(node: dict, occlusion_map: dict[str, OcclusionInfo]) -> Optional[dict]:
    """
    Recursively filter a UI tree, removing fully occluded nodes.

    Also annotates partially occluded nodes with invisible_area info.

    Args:
        node: The UI tree node.
        occlusion_map: Map of bid to OcclusionInfo.

    Returns:
        Filtered node or None if fully occluded.
    """
    if not isinstance(node, dict):
        return node

    bid = node.get("bid")

    # Check if fully occluded
    if bid is not None and bid in occlusion_map:
        info = occlusion_map[bid]
        if info.is_fully_occluded:
            return None

    # Copy node
    filtered = {}
    for key, value in node.items():
        if key == "children":
            # Recursively filter children
            if isinstance(value, list):
                filtered_children = []
                for child in value:
                    filtered_child = filter_occluded_nodes(child, occlusion_map)
                    if filtered_child is not None:
                        filtered_children.append(filtered_child)
                if filtered_children:
                    filtered["children"] = filtered_children
        else:
            filtered[key] = value

    # Add invisible_area for partially occluded nodes
    if bid is not None and bid in occlusion_map:
        info = occlusion_map[bid]
        if info.is_partially_occluded and info.invisible_regions:
            filtered["invisible_area"] = info.invisible_regions

    return filtered


def is_element_occluded(
    ui_tree: dict,
    target_bid: str,
    fully_only: bool = True,
) -> bool:
    """
    Check if a specific element is occluded.

    Args:
        ui_tree: The root UI tree node.
        target_bid: The bid of the element to check.
        fully_only: If True, only returns True for fully occluded elements.
                   If False, returns True for any occlusion.

    Returns:
        True if the element is occluded (based on fully_only setting).
    """
    occlusion_map = compute_occlusion_precise(ui_tree)

    if target_bid not in occlusion_map:
        return False

    info = occlusion_map[target_bid]

    if fully_only:
        return info.is_fully_occluded
    else:
        return info.is_fully_occluded or info.is_partially_occluded


def get_elements_at_point(
    ui_tree: dict,
    x: float,
    y: float,
) -> list[tuple[str, float]]:
    """
    Get all elements at a specific point, sorted by z_index (topmost first).

    Args:
        ui_tree: The root UI tree node.
        x: X coordinate.
        y: Y coordinate.

    Returns:
        List of (bid, z_index) tuples, sorted by z_index descending.
    """
    nodes = collect_nodes_with_bounds(ui_tree)
    point = Rect(x=x, y=y, width=1, height=1)

    hits = []
    for node, rect, z_index, ancestors in nodes:
        bid = node.get("bid")
        if bid is None:
            continue

        if rect.intersects(point):
            hits.append((bid, z_index))

    # Sort by z_index descending (topmost first)
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


def get_topmost_element_at_point(
    ui_tree: dict,
    x: float,
    y: float,
) -> Optional[str]:
    """
    Get the topmost element at a specific point.

    Args:
        ui_tree: The root UI tree node.
        x: X coordinate.
        y: Y coordinate.

    Returns:
        The bid of the topmost element, or None if no element at that point.
    """
    hits = get_elements_at_point(ui_tree, x, y)
    return hits[0][0] if hits else None
