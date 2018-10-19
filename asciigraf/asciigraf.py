#############################################################################
# Copyright (c) 2017-present, Opus One Energy Solutions Corporation
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#############################################################################

from collections import OrderedDict
import re

import networkx

from asciigraf.point import Point


LEFT, RIGHT = Point(-1, 0), Point(1, 0)
ABOVE, BELOW = Point(0, -1), Point(0, 1)
TOP_LEFT, BOTTOM_RIGHT = Point(-1, -1), Point(1, 1)
BOTTOM_LEFT, TOP_RIGHT = Point(1, -1), Point(-1, 1)


EDGE_CHARS = {"\\", "-", "/", "|"}
EDGE_CHAR_NEIGHBOURS = {  # first point in tuple is the point parsed first
    "-":  [LEFT, RIGHT],
    "\\": [TOP_LEFT, BOTTOM_RIGHT],
    "/":  [BOTTOM_LEFT, TOP_RIGHT],
    "|":  [ABOVE, BELOW]
}

ABUTTING = {
    TOP_LEFT:   "\\",  ABOVE: "|",    TOP_RIGHT: "/",
    LEFT:        "-",                     RIGHT: "-",
    BOTTOM_LEFT: "/",  BELOW: "|", BOTTOM_RIGHT: "\\",
}

def graph_from_ascii(network_string):
    """ Produces a networkx graph, based on an ascii drawing
        of a network
    """
    nodes, labels = map_nodes_and_labels(network_string)

    edge_chars = map_edge_chars(network_string)
    patch_edge_chars_over_labels(labels, edge_chars)
    edge_chars = OrderedDict(sorted(edge_chars.items()))

    node_char_to_node = map_text_chars_to_text(nodes)
    label_char_to_label = map_text_chars_to_text(labels)
    edge_char_to_edge_map = {}  # {Point -> {"points": [], "nodes": []}}
    edges = []

    def get_abutting_edge_chars(pos):
        """ Iterates through edge chars and maps out the edge/label
            chars that abut them to form a line
        """
        els = set()

        # first, consider neighbors of our char (e.g. if our char
        # is '-' then any node or edge char to the left or right
        # is neighboring to the char at pos)
        for offset in EDGE_CHAR_NEIGHBOURS[edge_chars[pos]]:
            neighbor = pos + offset
            if neighbor in edge_chars or neighbor in node_char_to_node:
                els |= {neighbor}

        # second, consider chars to which this char could be a neighbor
        # (e.g. if the char below is a |, our char neighbors it regardless)
        for offset, valid_char in ABUTTING.items():
            if edge_chars.get(pos + offset, " ") == valid_char:
                els |= {pos + offset}

        # every edge char should end up with exactly 2 neighbors, or
        # we have a line that doesn't make sense
        if len(els) > 2 or len(els) < 2:
            error_map = map_to_string({
                **{
                    pos: edge_chars[pos] for pos in [pos, *els]
                    if pos in edge_chars
                },
            })
            raise InvalidEdgeError(f"Invalid edge at {pos}:\n{error_map}")

        return els


    edge_char_to_neighbors = {
        pos: (*get_abutting_edge_chars(pos),)
        for pos in edge_chars.keys()
    }

    def build_edge_from_position(starting_char_position):
        def follow_edge(starting_position, neighbor):
            if neighbor in node_char_to_node:
                return (neighbor,)
            else:
                a, b = edge_char_to_neighbors[neighbor]
                next_neighbor = a if b == starting_position else b
                return (neighbor, *follow_edge(neighbor, next_neighbor))

        neighbor_1, neighbor_2 = sorted(edge_char_to_neighbors[pos])
        node_1, *positions, node_2 = [
            *reversed(follow_edge(pos, neighbor_1)), pos,
            *follow_edge(pos, neighbor_2)
        ]
        if node_1 > node_2:
            node_1, node_2 = node_2, node_1
            positions = [*reversed(positions)]

        new_edge = dict(
            points=positions,
            nodes=(node_char_to_node[node_1], node_char_to_node[node_2]),
        )
        return new_edge

    for pos, char in edge_chars.items():
        if pos in edge_char_to_edge_map:
            # We only expect to get past this continue for one char
            # in each edge -- if the above condition is false, we'll
            # do the below code and all the characters that are in 
            continue

        new_edge = build_edge_from_position(pos)

        for position in new_edge['points']:
            edge_char_to_edge_map[position] = new_edge
        edges.append(new_edge)

    ascii_graph = networkx.OrderedGraph()
    ascii_graph.add_nodes_from(
        (node, {"position": position}) for position, node in nodes.items()
    )
    ascii_graph.add_edges_from(
        (*edge['nodes'], {"length": len(edge["points"])})
        for edge in edges
    )
    networkx.set_edge_attributes(
        ascii_graph, name="label",
        values={
            edge_char_to_edge_map[pos]["nodes"]: label[1:-1]
            for pos, label in label_char_to_label.items()
            if pos in edge_char_to_edge_map
        }
    )
    return ascii_graph


def map_nodes_and_labels(network_string):
    """ Map the root position of nodes and labels
        to the node / label text.

        e.g. map_nodes_and_labels("  n1--(label1)--n2  ") -> {
            Point(2, 0): "n1",
            Point(6, 0): "(label1)",
            Point(16, 0): "n2",
        }
    """
    ascii_nodes = list(node_iter(network_string))
    nodes = OrderedDict()  # of the form {Point -> 'node_name'}
    labels = OrderedDict()  # of the form {Point -> 'label'}
    for ascii_label, root_position in ascii_nodes:
        if ascii_label.startswith("(") and ascii_label.endswith(")"):
            labels[root_position] = ascii_label
        else:
            nodes[root_position] = ascii_label
    return nodes, labels


def patch_edge_chars_over_labels(labels, edge_chars):
    """ Adds in edge chars where labels crossed an edge

        e.g.

        ---(horizontal_label)---

                becomes

        ------------------------

        e.g.
                |                         |
          (vertical_label)   becomes      |
                |                         |
    """

    label_chars = OrderedDict(
        (root_position + Point(i, 0), char)
        for root_position, label in labels.items()
        for i, char in enumerate(label)
    )
    for position, label_character in label_chars.items():
        above = position + Point(0, -1)
        below = position + Point(0, 1)
        left = position + Point(-1, 0)
        right = position + Point(1, 0)

        if label_character == "(":
            if edge_chars.get(left, "") == "-":
                edge_chars[position] = "-"
        elif label_character == ")":
            if edge_chars.get(right, "") == "-":
                edge_chars[position] = "-"
        elif edge_chars.get(above, "") == "|" and edge_chars.get(below, "") == "|":
            edge_chars[position] = "|"
        else:
            if edge_chars.get(left, "") == '-':
                edge_chars[position] = '-'


def char_map(text, root_position):
        """ Maps the position of each character in 'text'

            e.g.

            char_map("foo", root_position=Point(20, 2)) -> {
                Point(20, 2) -> 'f',
                Point(21, 2) -> 'o',
                Point(22, 2) -> 'o',
            }
        """
        return OrderedDict(
            (Point(root_position.x+x, root_position.y), char)
            for x, char in enumerate(text)
        )


def map_text_chars_to_text(text_map):
    """ Maps characters in text elements to the text elements

        e.g.

        text_map = {
            Point(1, 2): 'foo',
            Point(3, 4):  'bar',
        }

        map_text_chars_to_text(text_map) -> {
            Point(1, 2): 'foo',
            Point(2, 2): 'foo',
            Point(3, 2): 'foo',
            Point(3, 4): 'bar',
            Point(4, 4): 'bar',
            Point(5, 4): 'bar',
        }
    """
    return OrderedDict(
        (position, text)
        for root_position, text in text_map.items()
        for position, _ in char_map(text, root_position).items()
    )



def map_edge_chars(network_string):
    """ Map positions in the string to edge chars

        e.g. map_edge_chars("  --|   ") -> {
            Point(3,0): "-",
            Point(4,0): "-",
            Point(5,0): "|",
        }
    """
    return OrderedDict(
        (Point(col, row), char)
        for row, line in enumerate(network_string.split("\n"))
        for col, char in enumerate(line)
        if char in EDGE_CHARS
    )


def node_iter(network_string):
    for row, line in enumerate(network_string.split("\n")):
        for match in re.finditer('\(?([0-9A-Za-z_{}]+)\)?', line):
            yield (match.group(0), Point(match.start(), row))


class InvalidEdgeError(Exception):
    """ Raise this when an edge is wrongly drawn """


def map_to_string(char_map, node_chars=None):
    """ Redraws a char_map and node_char map """
    node_chars = node_chars or {}
    node_start_map = OrderedDict()
    for position, node_label in node_chars.items():
        if node_label not in node_start_map:
            node_start_map[node_label] = position
        else:
            if position < node_start_map[node_label]:
                node_start_map[node_label] = position

    all_chars = sorted(
        [*{val: key for key, val in node_start_map.items()}.items(),
         *char_map.items()],
        key=lambda x: x[0]
    )

    string = ""
    cursor = Point(0, 0)
    for position, label in all_chars:
        if cursor.y < position.y:
            string += '\n' * (position.y - cursor.y)
            cursor = Point(0, position.y)
        if cursor.x < position.x:
            string += ' ' * (position.x - cursor.x)
            cursor = Point(*position)
        string += label
        cursor.x += len(label)
    return string
