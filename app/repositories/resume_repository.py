from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from models.resume import ResumeAnalysis, ResumeModel


class ResumeRepository:
    """Handles MongoDB operations for resume documents."""

    def __init__(self, collection: Collection):
        """Initialize the repository with a MongoDB collection."""
        self.collection = collection

    def find_by_id(self, resume_id: str, user_id: str) -> ResumeModel | None:
        """Fetch a resume owned by ``user_id`` by its ObjectId.

        Returns ``None`` if the id is malformed or the document does not
        exist for this user.
        """
        try:
            doc = self.collection.find_one(
                {"_id": ObjectId(resume_id), "user_id": user_id}
            )
        except (InvalidId, PyMongoError):
            return None

        if doc is None:
            return None

        doc["id"] = str(doc["_id"])
        return ResumeModel.model_validate(doc)

    def update_analysis(
        self,
        resume_id: str,
        user_id: str,
        analysis: ResumeAnalysis,
    ) -> bool:
        """Write the extracted analysis onto the resume document.

        Returns ``True`` if the document was matched and updated.
        """
        now = datetime.now(UTC)
        result = self.collection.update_one(
            {"_id": ObjectId(resume_id), "user_id": user_id},
            {
                "$set": {
                    "analysis": analysis.model_dump(
                        by_alias=True,
                        exclude_none=True,
                    ),
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1
