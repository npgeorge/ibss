"""
Skill Loader Service

Loads and parses skill definitions from markdown and YAML files.
Skills encode domain knowledge (like Jesse Stine's Superstock methodology)
in human-readable format that can be versioned and audited.
"""
import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class CriterionDefinition:
    """Definition of a single scoring criterion"""
    name: str
    weight: float
    description: str
    scoring_rules: Dict[str, int]
    entry_signals: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    raw_content: str = ""


@dataclass
class InvestorProfile:
    """Investor profile with customized weights and filters"""
    name: str
    description: str
    min_score: int
    min_criteria_met: int
    weight_adjustments: Dict[str, float]
    filters: Dict[str, Any]
    preferred_signals: List[str]
    risk: Dict[str, Any]
    market_conditions: Dict[str, Any]


@dataclass
class SkillDefinition:
    """Complete skill definition loaded from files"""
    name: str
    description: str
    core_principles: List[str]
    criteria: Dict[str, CriterionDefinition]
    profiles: Dict[str, InvestorProfile]
    entry_signals: Dict[str, str]
    raw_content: str = ""


class SkillLoader:
    """
    Loads skill definitions from markdown and YAML files.

    Directory structure expected:
    skills/
      superstock/
        SKILL.md           # Main skill overview
        criteria/
          magic_line.md    # Individual criterion definitions
          insider_buying.md
          ...
        profiles/
          aggressive.yaml  # Investor profiles
          conservative.yaml
    """

    def __init__(self, skills_dir: Optional[str] = None):
        if skills_dir is None:
            # Default to skills directory relative to backend
            base_dir = Path(__file__).parent.parent.parent
            skills_dir = base_dir / "skills"
        self.skills_dir = Path(skills_dir)
        self._cache: Dict[str, SkillDefinition] = {}

    def load_skill(self, skill_name: str, force_reload: bool = False) -> SkillDefinition:
        """
        Load a skill definition by name.

        Args:
            skill_name: Name of the skill directory (e.g., "superstock")
            force_reload: If True, bypass cache and reload from files

        Returns:
            SkillDefinition with all criteria and profiles loaded
        """
        if not force_reload and skill_name in self._cache:
            return self._cache[skill_name]

        skill_path = self.skills_dir / skill_name
        if not skill_path.exists():
            raise ValueError(f"Skill not found: {skill_name}")

        # Load main skill file
        main_file = skill_path / "SKILL.md"
        if not main_file.exists():
            raise ValueError(f"Missing SKILL.md for skill: {skill_name}")

        main_content = main_file.read_text()

        # Parse main skill overview
        description = self._extract_section(main_content, "Overview")
        principles = self._extract_list_section(main_content, "Core Principles")
        entry_signals = self._extract_entry_signals(main_content)

        # Load criteria definitions
        criteria = self._load_criteria(skill_path / "criteria")

        # Load profiles
        profiles = self._load_profiles(skill_path / "profiles")

        skill = SkillDefinition(
            name=skill_name,
            description=description,
            core_principles=principles,
            criteria=criteria,
            profiles=profiles,
            entry_signals=entry_signals,
            raw_content=main_content
        )

        self._cache[skill_name] = skill
        return skill

    def _load_criteria(self, criteria_dir: Path) -> Dict[str, CriterionDefinition]:
        """Load all criterion definition files from directory"""
        criteria = {}

        if not criteria_dir.exists():
            return criteria

        for md_file in criteria_dir.glob("*.md"):
            criterion = self._parse_criterion(md_file)
            if criterion:
                criteria[criterion.name] = criterion

        return criteria

    def _parse_criterion(self, filepath: Path) -> Optional[CriterionDefinition]:
        """Parse a single criterion markdown file"""
        content = filepath.read_text()

        # Extract name from filename or header
        name = filepath.stem.replace("_", " ").title()

        # Try to extract from H1 header
        h1_match = re.search(r'^# (.+?)(?:\s+Criterion)?$', content, re.MULTILINE)
        if h1_match:
            name = h1_match.group(1).strip()

        # Extract weight
        weight = 0.05  # default
        weight_match = re.search(r'Weight:\s*(\d+(?:\.\d+)?)\s*%', content, re.IGNORECASE)
        if weight_match:
            weight = float(weight_match.group(1)) / 100

        # Extract description
        description = self._extract_section(content, "Description")

        # Extract scoring rules from tables
        scoring_rules = self._extract_scoring_table(content)

        # Extract entry signals
        entry_signals = self._extract_list_section(content, "Entry Signal")

        # Extract red flags
        red_flags = self._extract_list_section(content, "Red Flags")

        return CriterionDefinition(
            name=name,
            weight=weight,
            description=description,
            scoring_rules=scoring_rules,
            entry_signals=entry_signals,
            red_flags=red_flags,
            raw_content=content
        )

    def _load_profiles(self, profiles_dir: Path) -> Dict[str, InvestorProfile]:
        """Load all investor profiles from directory"""
        profiles = {}

        if not profiles_dir.exists():
            return profiles

        for yaml_file in profiles_dir.glob("*.yaml"):
            profile = self._parse_profile(yaml_file)
            if profile:
                profiles[profile.name.lower()] = profile

        return profiles

    def _parse_profile(self, filepath: Path) -> Optional[InvestorProfile]:
        """Parse an investor profile YAML file"""
        with open(filepath) as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        return InvestorProfile(
            name=data.get("name", filepath.stem),
            description=data.get("description", ""),
            min_score=data.get("min_score", 60),
            min_criteria_met=data.get("min_criteria_met", 8),
            weight_adjustments=data.get("weight_adjustments", {}),
            filters=data.get("filters", {}),
            preferred_signals=data.get("preferred_signals", []),
            risk=data.get("risk", {}),
            market_conditions=data.get("market_conditions", {})
        )

    def _extract_section(self, content: str, section_name: str) -> str:
        """Extract content under a markdown header"""
        # Match ## Section Name or ### Section Name
        pattern = rf'##+ {re.escape(section_name)}\s*\n(.*?)(?=\n##|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_list_section(self, content: str, section_name: str) -> List[str]:
        """Extract a bulleted list from a section"""
        section = self._extract_section(content, section_name)
        if not section:
            return []

        # Extract bullet points
        items = []
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith(('-', '*', '•')):
                item = re.sub(r'^[-*•]\s*', '', line)
                # Extract bold part as key
                bold_match = re.match(r'\*\*(.+?)\*\*', item)
                if bold_match:
                    items.append(bold_match.group(1))
                else:
                    items.append(item)

        return items

    def _extract_scoring_table(self, content: str) -> Dict[str, int]:
        """Extract scoring rules from markdown tables"""
        rules = {}

        # Find tables (| header | header |)
        table_pattern = r'\|(.+)\|.+\|[\s\S]*?(?=\n\n|\Z)'
        tables = re.findall(table_pattern, content)

        # Parse each row
        for line in content.split('\n'):
            if '|' in line and not line.strip().startswith('|--'):
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2:
                    condition = parts[0]
                    try:
                        score = int(parts[-1])
                        rules[condition] = score
                    except ValueError:
                        pass

        return rules

    def _extract_entry_signals(self, content: str) -> Dict[str, str]:
        """Extract entry signals from main skill file"""
        signals = {}

        section = self._extract_section(content, "Entry Signals")
        if not section:
            return signals

        # Parse numbered list
        for line in section.split('\n'):
            match = re.match(r'^\d+\.\s+\*\*(.+?)\*\*:\s*(.+)$', line.strip())
            if match:
                signal_name = match.group(1).lower().replace(' ', '_')
                signal_desc = match.group(2)
                signals[signal_name] = signal_desc

        return signals

    def get_profile_weights(self, skill_name: str, profile_name: str) -> Dict[str, float]:
        """
        Get adjusted criterion weights for a specific profile.

        Returns base weights multiplied by profile adjustments.
        """
        skill = self.load_skill(skill_name)
        profile = skill.profiles.get(profile_name.lower())

        if not profile:
            raise ValueError(f"Profile not found: {profile_name}")

        # Start with base weights from criteria
        weights = {}
        for criterion_key, criterion in skill.criteria.items():
            weights[criterion_key] = criterion.weight

        # Apply profile adjustments
        for criterion_key, multiplier in profile.weight_adjustments.items():
            if criterion_key in weights:
                weights[criterion_key] *= multiplier

        # Normalize to sum to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def list_skills(self) -> List[str]:
        """List all available skills"""
        if not self.skills_dir.exists():
            return []

        return [
            d.name for d in self.skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    def list_profiles(self, skill_name: str) -> List[str]:
        """List all profiles for a skill"""
        skill = self.load_skill(skill_name)
        return list(skill.profiles.keys())


# Singleton instance
_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """Get the global skill loader instance"""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader


def load_superstock_skill() -> SkillDefinition:
    """Convenience function to load the Superstock skill"""
    return get_skill_loader().load_skill("superstock")
