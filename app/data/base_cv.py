"""
Santiago Hurtado Lopez — Base CV data with real experience.

Each experience entry has real_technologies/real_achievements context
that is sent to AI for intelligent tech-swapping, but NOT shown in final CV.
"""

from app.models.schemas import CVData, ContactInfo, ExperienceEntry, EducationEntry


# ── Real context per company (sent to AI, NOT shown in final CV) ─────────────
EXPERIENCE_CONTEXT = {
    "Bit Colombia": {
        "real_technologies": [
            "PHP", "WordPress", "Linux", "Oracle Cloud (OCI)", "AWS",
            "MySQL", "Apache", "Nginx", "Docker", "Git", "cPanel",
            "HTML", "CSS", "JavaScript",
        ],
        "real_achievements": [
            "Led complete production environment redesign, migrating infrastructure on OCI and AWS, achieving 10x speed improvement",
            "Managed and maintained a full production website end-to-end as sole responsible developer",
            "Coordinated multidisciplinary team including designers, DB specialists, and infrastructure",
            "Managed large-scale WordPress projects ensuring stability and professional standards",
            "Implemented UI/UX improvements and optimizations that reduced load time by 10x",
            "Deep Linux administration: server config, deployments, security, automation",
            "Modernized legacy technology stack with significant performance gains",
        ],
    },
    "Grupo Vidawa": {
        "real_technologies": [
            "Vue.js", "JavaScript", "TypeScript", "CSS", "HTML",
            "CI/CD", "Git", "REST APIs",
        ],
        "real_achievements": [
            "Developed frontend interfaces for enterprise administrative panels",
            "Coordinated with external teams building enterprise applications",
            "Implemented CI/CD integration pipelines",
            "Created and maintained automated tests",
            "Built modular UI components following UX/UI principles",
        ],
    },
    "FianzaCredito": {
        "real_technologies": [
            "Python", "Django", "REST APIs", "Docker", "AWS",
            "AWS Lambda", "Node.js", "Express", "PostgreSQL",
        ],
        "real_achievements": [
            "Modernized application infrastructure using Docker and AWS, including serverless migration with AWS Lambda",
            "Developed APIs for credit evaluation",
            "Built and maintained critical applications with continuous improvements",
            "Integrated external providers and scoring services",
            "Explored and evaluated low-code Python frameworks for optimization",
        ],
    },
}


def get_base_cv() -> CVData:
    """Return Santiago's base CV data with real information."""
    return CVData(
        contact=ContactInfo(
            name="Santiago Hurtado Lopez",
            email="Sanhurtadolopez@outlook.com",
            phone="(+57) 3126714038",
            location="Cali, Colombia",
            linkedin="",
            website="moonhellal.com",
            github="github.com/Desstter",
        ),
        summary=(
            "Desarrollador Full-Stack con 5 años de experiencia creando y manteniendo "
            "sistemas escalables en entornos de producción. Experiencia sólida en arquitecturas "
            "en la nube (OCI, AWS), integraciones con APIs REST y despliegues automatizados. "
            "Apasionado por la inteligencia artificial aplicada a productos reales. "
            "Reconocido por mi capacidad para optimizar rendimiento, liderar equipos técnicos "
            "y trabajar en entornos 100% remotos y colaborativos."
        ),
        experience=[
            ExperienceEntry(
                company="Bit Colombia",
                title="Líder Técnico / Fullstack Developer",
                dates="Ago 2023 – Ene 2026",
                location="Remoto",
                description=(
                    "• Lideré el rediseño completo del entorno de producción en la nube, migrando y modernizando infraestructura en Oracle Cloud (OCI) y AWS, logrando una mejora de 10x en velocidad y rendimiento.\n"
                    "• Encargado de la coordinación de un equipo multidisciplinario (incluyendo diseñadores y especialistas en bases de datos), asegurando la calidad y escalabilidad de los proyectos.\n"
                    "• Gestioné proyectos WordPress a gran escala, asegurando estabilidad y manteniendo estándares de desarrollo profesional.\n"
                    "• Implementé mejoras de UI/UX y optimizaciones que redujeron el tiempo de carga en 10X."
                ),
                technologies=["PHP", "WordPress", "Linux", "Oracle Cloud", "AWS", "MySQL", "Docker"],
            ),
            ExperienceEntry(
                company="Grupo Vidawa",
                title="Frontend Developer",
                dates="May 2022 – Oct 2022",
                location="Remoto",
                description=(
                    "• Desarrollé interfaces para paneles administrativos empresariales.\n"
                    "• Construí componentes modulares integrando principios de UX/UI.\n"
                    "• Coordiné con equipos externos creando aplicaciones empresariales.\n"
                    "• Integré pipelines de CI/CD y participé en la creación de pruebas automatizadas."
                ),
                technologies=["Vue.js", "JavaScript", "TypeScript", "CSS", "CI/CD", "Git"],
            ),
            ExperienceEntry(
                company="FianzaCredito",
                title="Fullstack Developer",
                dates="Nov 2021 – Abr 2022",
                location="Remoto",
                description=(
                    "• Dirigí la modernización de la infraestructura de aplicaciones utilizando Docker y AWS, incluyendo migración a arquitecturas serverless con AWS Lambda.\n"
                    "• Desarrollé APIs para evaluación crediticia.\n"
                    "• Desarrollé y mantuve aplicaciones críticas, incorporando mejoras continuas y funcionalidades avanzadas.\n"
                    "• Integré proveedores externos y servicios de scoring."
                ),
                technologies=["Python", "Django", "Docker", "AWS", "AWS Lambda", "REST APIs"],
            ),
        ],
        education=[
            EducationEntry(
                institution="SENA",
                degree="Técnico en Programación de Software",
                dates="Sep 2017 – Ene 2020",
                details="",
            ),
        ],
        projects=[],
        skills=[
            "PHP", "Python", "JavaScript", "TypeScript", "Vue.js",
            "Django", "WordPress", "Linux", "Docker",
            "AWS", "Oracle Cloud (OCI)", "MySQL", "PostgreSQL",
            "REST APIs", "Git", "CI/CD", "HTML", "CSS",
        ],
        certifications=[],
        languages=["Español (Nativo)", "Inglés (Intermedio)"],
        raw_markdown="",
        detected_language="es",
    )
