class BTreeNode:
    def __init__(self, leaf: bool = False):
        """
        A single node in the B-Tree.

        keys:     sorted list of values (what we search on)
        values:   list of row lists corresponding to each key
        children: list of child BTreeNode pointers (empty if leaf)
        leaf:     True if this node has no children
        """
        self.keys = []
        self.values = []  # each entry is a list of rows with that key
        self.children = []
        self.leaf = leaf


class BTree:
    # Maximum number of keys per node.
    # When a node exceeds this, it splits - core B-Tree behavior.
    ORDER = 3

    def __init__(self):
        # Tree always starts with a single empty leaf node as root
        self.root = BTreeNode(leaf=True)

    def insert(self, key, row: list):
        """
        Insert a key-row pair into the tree.
        If the root is full, split it first and grow the tree upward.
        """
        root = self.root

        if len(root.keys) == (2 * self.ORDER) - 1:
            # Root is full - create new root and split old one
            new_root = BTreeNode(leaf=False)
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root

        self._insert_non_full(self.root, key, row)

    def _insert_non_full(self, node: BTreeNode, key, row: list):
        """
        Insert into a node that is guaranteed not full.
        Recurses down to the correct leaf position.
        """
        i = len(node.keys) - 1

        if node.leaf:
            # Find correct sorted position and insert
            if key in node.keys:
                # Key exists - append row to existing key's list (non-unique index)
                idx = node.keys.index(key)
                node.values[idx].append(row)
            else:
                # Insert new key in sorted order
                node.keys.append(None)
                node.values.append(None)

                while i >= 0 and key < node.keys[i]:
                    node.keys[i + 1] = node.keys[i]
                    node.values[i + 1] = node.values[i]
                    i -= 1

                node.keys[i + 1] = key
                node.values[i + 1] = [row]
        else:
            # Internal node - find correct child to descend into
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1

            # Split child if full before descending
            if len(node.children[i].keys) == (2 * self.ORDER) - 1:
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1

            self._insert_non_full(node.children[i], key, row)

    def _split_child(self, parent: BTreeNode, i: int):
        """
        Split the i-th child of parent into two nodes.
        The median key is promoted up to the parent.
        This is what keeps the tree balanced.
        """
        order = self.ORDER
        child = parent.children[i]
        new_node = BTreeNode(leaf=child.leaf)

        # Median index
        mid = order - 1

        # Promote median key to parent
        parent.keys.insert(i, child.keys[mid])
        parent.values.insert(i, child.values[mid])
        parent.children.insert(i + 1, new_node)

        # Right half goes to new node
        new_node.keys = child.keys[mid + 1:]
        new_node.values = child.values[mid + 1:]

        # Left half stays in original child
        child.keys = child.keys[:mid]
        child.values = child.values[:mid]

        # Split children pointers if internal node
        if not child.leaf:
            new_node.children = child.children[mid + 1:]
            child.children = child.children[:mid + 1]

    def search(self, key) -> list:
        """
        Return all rows matching key, or empty list if not found.
        O(log n) lookup - the core payoff of the index.
        """
        return self._search(self.root, key)

    def _search(self, node: BTreeNode, key) -> list:
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1

        if i < len(node.keys) and key == node.keys[i]:
            return node.values[i]

        if node.leaf:
            return []

        return self._search(node.children[i], key)

    def delete(self, key, row: list):
        """
        Remove a specific row from the index entry for key.
        If no rows remain for that key, remove the key entirely.
        """
        self._delete_row(self.root, key, row)

    def _delete_row(self, node: BTreeNode, key, row: list):
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1

        if i < len(node.keys) and key == node.keys[i]:
            # Found the key - remove the specific row
            if row in node.values[i]:
                node.values[i].remove(row)

            # If no rows left for this key, remove the key too
            if not node.values[i]:
                node.keys.pop(i)
                node.values.pop(i)
            return

        if not node.leaf:
            self._delete_row(node.children[i], key, row)

    def all_rows(self) -> list:
        """
        In-order traversal - returns all indexed rows sorted by key.
        Used later for ORDER BY support.
        """
        result = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node: BTreeNode, result: list):
        if node.leaf:
            for row_list in node.values:
                result.extend(row_list)
            return

        for i, row_list in enumerate(node.values):
            self._inorder(node.children[i], result)
            result.extend(row_list)

        self._inorder(node.children[-1], result)
