import json
from gltest.types import MockedWebResponseData


def test_create_bounty(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Implement Token Escrow",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Must support deposit and withdraw with reentrancy protection.",
            reward_amount=1000,
        )

    assert bounty_id == "bounty_1"
    assert contract.get_bounty_count() == 1
    assert contract.get_bounty_id_at(0) == "bounty_1"
    bounty = contract.get_bounty(bounty_id)
    assert bounty.title == "Implement Token Escrow"
    assert bounty.repo_url == "https://github.com/example/repo"
    assert bounty.status == "OPEN"
    assert bounty.creator == direct_alice
    assert bounty.reward_amount == 1000
    assert bounty.created_at_block == 1


def test_create_bounty_validation_reverts(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("Bounty title cannot be empty"):
            contract.create_bounty(
                title="",
                repo_url="https://github.com/example/repo",
                acceptance_criteria="Some criteria",
                reward_amount=100,
            )

        with direct_vm.expect_revert("Repository URL cannot be empty"):
            contract.create_bounty(
                title="Task",
                repo_url="",
                acceptance_criteria="Some criteria",
                reward_amount=100,
            )

        with direct_vm.expect_revert("Repository URL must begin with http:// or https://"):
            contract.create_bounty(
                title="Task",
                repo_url="ftp://github.com/example/repo",
                acceptance_criteria="Some criteria",
                reward_amount=100,
            )

        with direct_vm.expect_revert("Acceptance criteria cannot be empty"):
            contract.create_bounty(
                title="Task",
                repo_url="https://github.com/example/repo",
                acceptance_criteria="   ",
                reward_amount=100,
            )


def test_submit_pr_accepted_and_validator_consensus(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Implement Authentication",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Must support JWT validation and error handling.",
            reward_amount=500,
        )

    direct_vm.mock_web(".*", MockedWebResponseData(
        method="GET",
        status=200,
        body="diff --git a/auth.py b/auth.py\n+ def verify_jwt(token): return True",
    ))
    direct_vm.mock_llm(".*", json.dumps({
        "verdict": "ACCEPTED",
        "reason": "The PR implements JWT verification with proper error handling.",
    }))

    with direct_vm.prank(direct_bob):
        res_raw = contract.submit_pr_for_evaluation(
            bounty_id=bounty_id,
            pr_url="https://github.com/example/repo/pull/42",
        )

    res = json.loads(res_raw)
    assert res["verdict"] == "ACCEPTED"
    assert res["bounty_status"] == "COMPLETED"

    bounty = contract.get_bounty(bounty_id)
    assert bounty.status == "COMPLETED"
    assert bounty.winner == direct_bob
    assert bounty.accepted_pr_url == "https://github.com/example/repo/pull/42"
    assert bounty.created_at_block == 1
    submission = contract.get_submission("sub_1")
    assert submission.submitted_at_block == 1

    agreed = direct_vm.run_validator()
    assert agreed is True


def test_submit_pr_revisions_needed(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Write Comprehensive Tests",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Must reach 90% test coverage.",
            reward_amount=300,
        )

    direct_vm.mock_web(".*", MockedWebResponseData(
        method="GET",
        status=200,
        body="diff --git a/test.py...",
    ))
    direct_vm.mock_llm(".*", json.dumps({
        "verdict": "REVISIONS_NEEDED",
        "reason": "Test coverage is only at 75%, additional edge case tests needed.",
    }))

    with direct_vm.prank(direct_bob):
        res_raw = contract.submit_pr_for_evaluation(
            bounty_id=bounty_id,
            pr_url="https://github.com/example/repo/pull/10",
        )

    res = json.loads(res_raw)
    assert res["verdict"] == "REVISIONS_NEEDED"
    assert res["bounty_status"] == "OPEN"

    bounty = contract.get_bounty(bounty_id)
    assert bounty.status == "OPEN"
    assert bounty.total_submissions == 1


def test_submit_pr_rejected(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Optimize DB Query",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Must reduce query latency by 50%.",
            reward_amount=200,
        )

    direct_vm.mock_web(".*", MockedWebResponseData(
        method="GET",
        status=200,
        body="diff --git a/db.py...",
    ))
    direct_vm.mock_llm(".*", json.dumps({
        "verdict": "REJECTED",
        "reason": "Changes introduced syntax errors and failed to optimize queries.",
    }))

    with direct_vm.prank(direct_bob):
        res_raw = contract.submit_pr_for_evaluation(
            bounty_id=bounty_id,
            pr_url="https://github.com/example/repo/pull/99",
        )

    res = json.loads(res_raw)
    assert res["verdict"] == "REJECTED"
    assert res["bounty_status"] == "OPEN"

    bounty = contract.get_bounty(bounty_id)
    assert bounty.status == "OPEN"


def test_creator_cannot_claim_own_bounty(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Task",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Criteria",
            reward_amount=100,
        )
        with direct_vm.expect_revert("Bounty creator cannot submit PR to their own bounty"):
            contract.submit_pr_for_evaluation(
                bounty_id=bounty_id,
                pr_url="https://github.com/example/repo/pull/1",
            )


def test_cancel_bounty_and_access_control(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Temporary Task",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Criteria",
            reward_amount=100,
        )

    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("Unauthorized: only creator or contract owner can cancel bounty"):
            contract.cancel_bounty(bounty_id=bounty_id)

    with direct_vm.prank(direct_alice):
        contract.cancel_bounty(bounty_id=bounty_id)

    bounty = contract.get_bounty(bounty_id)
    assert bounty.status == "CANCELLED"

    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("Bounty is not open for submissions. Current status: CANCELLED"):
            contract.submit_pr_for_evaluation(
                bounty_id=bounty_id,
                pr_url="https://github.com/example/repo/pull/1",
            )


def test_evaluate_pr_standalone(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/contract.py")
    direct_vm.mock_web(".*", MockedWebResponseData(
        method="GET",
        status=200,
        body="diff --git a/main.py...",
    ))
    direct_vm.mock_llm(".*", json.dumps({
        "verdict": "ACCEPTED",
        "reason": "Clean code changes meeting all criteria.",
    }))

    raw_result = contract.evaluate_pr_standalone(
        pr_url="https://github.com/example/repo/pull/123",
        acceptance_criteria="Implement feature X.",
    )
    result = json.loads(raw_result)
    assert result["verdict"] == "ACCEPTED"
    assert result["pr_url"] == "https://github.com/example/repo/pull/123"
    assert "reason" in result


def test_submit_pr_unrelated_repo_reverts(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/contract.py")
    with direct_vm.prank(direct_alice):
        bounty_id = contract.create_bounty(
            title="Implement Security Feature",
            repo_url="https://github.com/example/repo",
            acceptance_criteria="Implement secure token transfer.",
            reward_amount=500,
        )

    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("Security Error: The submitted Pull Request does not belong to this bounty's repository."):
            contract.submit_pr_for_evaluation(
                bounty_id=bounty_id,
                pr_url="https://github.com/attacker/malicious-repo/pull/1",
            )

