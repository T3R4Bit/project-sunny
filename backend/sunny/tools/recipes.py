"""P12 — Recipe management and meal planning for Sunny.

Store recipes with ingredients, instructions, and nutritional info.
Generate meal plans and shopping lists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class RecipeIngredient:
    """A single ingredient in a recipe."""
    name: str
    amount: str = ""
    unit: str = ""
    optional: bool = False


@dataclass
class Recipe:
    """A recipe."""
    id: str
    title: str
    ingredients: list[RecipeIngredient] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    prep_time_minutes: int = 0
    cook_time_minutes: int = 0
    servings: int = 4
    category: str = "main"  # breakfast | lunch | dinner | snack | dessert
    tags: list[str] = field(default_factory=list)
    cuisine: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = ""
    difficulty: str = "easy"  # easy | medium | hard

    @property
    def total_time_minutes(self) -> int:
        return self.prep_time_minutes + self.cook_time_minutes

    def to_vault_line(self) -> str:
        parts = [f"recipe:{self.id}", f"title:{self.title}"]
        if self.cuisine:
            parts.append(f"cuisine:{self.cuisine}")
        parts.append(f"difficulty:{self.difficulty}")
        parts.append(f"time:{self.total_time_minutes}m")
        return " | ".join(parts)


class RecipesManager:
    """Manage recipes and generate meal plans."""

    def __init__(self, vault: Path) -> None:
        self.vault = vault
        self._recipes_dir = vault / "data" / "recipes"
        self._recipes_dir.mkdir(parents=True, exist_ok=True)

    def add_recipe(
        self,
        title: str,
        ingredients: list[RecipeIngredient],
        instructions: list[str],
        category: str = "main",
        prep_time: int = 0,
        cook_time: int = 0,
        servings: int = 4,
        tags: list[str] = None,
        cuisine: str = "",
        author: str = "",
        difficulty: str = "easy",
    ) -> Recipe:
        """Add a new recipe."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        recipe = Recipe(
            id=f"recipe-{title.lower().replace(' ', '-')[:30]}-{timestamp}",
            title=title,
            ingredients=ingredients,
            instructions=instructions,
            prep_time_minutes=prep_time,
            cook_time_minutes=cook_time,
            servings=servings,
            category=category,
            tags=tags or [],
            cuisine=cuisine,
            author=author,
            difficulty=difficulty,
        )

        filepath = self._recipes_dir / f"{recipe.id}.md"
        filepath.write_text(self._render_recipe(recipe), encoding="utf-8")
        log.info("Added recipe: %s", recipe.id)
        return recipe

    def find_recipes(
        self,
        query: str = "",
        category: str = "",
        tags: list[str] = None,
        max_time: int = 0,
    ) -> list[Recipe]:
        """Find recipes matching criteria."""
        results = []
        if not self._recipes_dir.exists():
            return results

        for f in self._recipes_dir.glob("*.md"):
            recipe = self._load_recipe(f)
            if not recipe:
                continue

            if query:
                query_lower = query.lower()
                if (query_lower not in recipe.title.lower() and
                    not any(query_lower in ing.name.lower() for ing in recipe.ingredients)):
                    continue

            if category and recipe.category != category:
                continue

            if tags and not any(t in recipe.tags for t in tags):
                continue

            if max_time > 0 and recipe.total_time_minutes > max_time:
                continue

            results.append(recipe)

        return results

    def generate_meal_plan(
        self,
        days: int = 7,
        categories: list[str] = None,
        max_meals_per_day: int = 3,
    ) -> dict[str, list[Recipe]]:
        """Generate a meal plan for the next N days."""
        import random
        from datetime import timedelta

        available = self.find_recipes()
        if not available:
            return {}

        if categories:
            available = [r for r in available if r.category in categories]

        plan = {}
        today = datetime.now(timezone.utc).date()

        for i in range(days):
            date = today + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            meals = []

            # Pick random recipes for each meal slot
            used = set(m.id for m in meals)
            shuffled = available[:]
            random.shuffle(shuffled)

            for recipe in shuffled:
                if recipe.id not in used and len(meals) < max_meals_per_day:
                    meals.append(recipe)
                    used.add(recipe.id)

            plan[date_str] = meals

        return plan

    def generate_shopping_list(
        self,
        meal_plan: dict[str, list[Recipe]],
    ) -> dict[str, list[str]]:
        """Generate a shopping list from a meal plan."""
        shopping: dict[str, list[str]] = {"ingredients": [], "notes": []}

        for date, meals in meal_plan.items():
            for meal in meals:
                for ing in meal.ingredients:
                    item = f"{ing.amount} {ing.unit} {ing.name}".strip()
                    if item not in shopping["ingredients"]:
                        shopping["ingredients"].append(item)
                    if ing.optional:
                        shopping["notes"].append(f"Optional: {ing.name}")

        return shopping

    def _load_recipe(self, filepath: Path) -> Optional[Recipe]:
        """Load a recipe from its markdown file."""
        try:
            content = filepath.read_text(encoding="utf-8")
            title = ""
            ingredients = []
            instructions = []
            prep_time = 0
            cook_time = 0
            servings = 4
            category = "main"
            tags = []
            cuisine = ""
            difficulty = "easy"

            reading = None  # "ingredients" | "instructions"
            for line in content.split("\n"):
                stripped = line.strip()

                if stripped.startswith("# "):
                    title = stripped[2:]
                    reading = None
                elif stripped.startswith("ingredients:"):
                    reading = "ingredients"
                elif stripped.startswith("instructions:"):
                    reading = "instructions"
                elif stripped.startswith("### ") and "ingredients" not in stripped.lower():
                    reading = None
                elif stripped.startswith("## ") and "instructions" not in stripped.lower():
                    reading = None
                elif reading == "ingredients" and stripped.startswith("- "):
                    name = stripped[2:].strip()
                    ingredients.append(RecipeIngredient(name=name))
                elif reading == "instructions" and stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.")):
                    instruction = stripped.split(".", 1)[1].strip()
                    instructions.append(instruction)
                elif stripped.startswith("prep_time:"):
                    try:
                        prep_time = int(stripped.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif stripped.startswith("cook_time:"):
                    try:
                        cook_time = int(stripped.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif stripped.startswith("servings:"):
                    try:
                        servings = int(stripped.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif stripped.startswith("category:"):
                    category = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("cuisine:"):
                    cuisine = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("difficulty:"):
                    difficulty = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("tags:"):
                    tag_str = stripped.split(":", 1)[1].strip()
                    tags = [t.strip() for t in tag_str.split(",") if t.strip()]

            if not title:
                title = filepath.stem.replace("recipe-", "").replace("-", " ").title()

            return Recipe(
                id=filepath.stem.replace(".md", ""),
                title=title,
                ingredients=ingredients,
                instructions=instructions,
                prep_time_minutes=prep_time,
                cook_time_minutes=cook_time,
                servings=servings,
                category=category,
                tags=tags,
                cuisine=cuisine,
                difficulty=difficulty,
            )
        except Exception as e:
            log.error("Failed to load recipe %s: %s", filepath, e)
            return None

    def _render_recipe(self, recipe: Recipe) -> str:
        lines = [
            f"# {recipe.title}",
            "",
            f"category: {recipe.category}",
            f"cuisine: {recipe.cuisine}",
            f"difficulty: {recipe.difficulty}",
            f"prep_time: {recipe.prep_time_minutes}",
            f"cook_time: {recipe.cook_time_minutes}",
            f"servings: {recipe.servings}",
            f"tags: {', '.join(recipe.tags)}",
            "",
            "ingredients:",
        ]
        for ing in recipe.ingredients:
            line = f"- {ing.name}"
            if ing.amount:
                line = f"- {ing.amount} {ing.unit} {ing.name}"
            if ing.optional:
                line += " (optional)"
            lines.append(line)

        lines.extend(["", "instructions:", ""])
        for i, instr in enumerate(recipe.instructions, 1):
            lines.append(f"{i}. {instr}")

        lines.append("")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        if not self._recipes_dir.exists():
            return {"total": 0}
        total = len(list(self._recipes_dir.glob("*.md")))
        return {"total": total}
