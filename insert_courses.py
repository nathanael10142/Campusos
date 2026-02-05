#!/usr/bin/env python3
"""
Insert sample courses into the database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import init_db, get_db

async def insert_sample_courses():
    """Insert sample courses"""
    await init_db()
    db = get_db()
    
    # Sample courses data
    courses = [
        {
            "name": "Algorithmique et Structures de Données",
            "code": "INFO101",
            "faculty": "Informatique",
            "academic_level": "L3",
            "professor": "Dr. Batera",
            "description": "Introduction aux algorithmes et structures de données"
        },
        {
            "name": "Bases de Données",
            "code": "INFO201",
            "faculty": "Informatique",
            "academic_level": "L3",
            "professor": "Dr. Batera",
            "description": "Conception et gestion des bases de données"
        },
        {
            "name": "Intelligence Artificielle",
            "code": "INFO301",
            "faculty": "Informatique",
            "academic_level": "M1",
            "professor": "Dr. Batera",
            "description": "Fondements de l'IA et apprentissage automatique"
        },
        {
            "name": "Réseaux Informatiques",
            "code": "INFO102",
            "faculty": "Informatique",
            "academic_level": "L3",
            "professor": "Dr. Batera",
            "description": "Architecture et protocoles réseau"
        },
        {
            "name": "Développement Web",
            "code": "INFO202",
            "faculty": "Informatique",
            "academic_level": "L3",
            "professor": "Dr. Batera",
            "description": "Technologies web modernes"
        }
    ]
    
    for course in courses:
        try:
            result = db.insert("courses", course)
            print(f"Inserted course: {course['name']}")
        except Exception as e:
            print(f"Error inserting {course['name']}: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(insert_sample_courses())